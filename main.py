import os
import json
import time
import random
import requests
import asyncio
import urllib.parse
from google import genai
import edge_tts

try:
    from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip, CompositeAudioClip, concatenate_videoclips
except ImportError:
    from moviepy.video.VideoClip import ImageClip
    from moviepy.audio.io.AudioFileClip import AudioFileClip
    from moviepy.video.VideoClip import TextClip
    from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
    from moviepy.audio.AudioClip import CompositeAudioClip
    from moviepy.video.compositing.concatenate import concatenate_videoclips

import google_auth_oauthlib.flow
import googleapiclient.discovery
from googleapiclient.http import MediaFileUpload

# 1. Проверка секретов
if not os.path.exists('client_secret.json'):
    with open('client_secret.json', 'w') as f:
        f.write(os.getenv('CLIENT_SECRET_JSON', ''))

if not os.path.exists('token.json'):
    with open('token.json', 'w') as f:
        f.write(os.getenv('YOUTUBE_TOKEN', ''))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

VIRAL_MEME_PRESETS = [
    {"topic": "Senior Dev vs Junior Dev in Code Review", "animal": "cute fluffy Pixar cat"},
    {"topic": "Deploying code on Friday at 5 PM", "animal": "Pixar style dog wearing hoodie"},
    {"topic": "Fixing 1 bug creates 10 new bugs", "animal": "panicking Pixar style cat programmer"},
    {"topic": "Trying to center a div with CSS", "animal": "crazy funny 3D Pixar dog at computer"},
    {"topic": "Client asking for a quick small change", "animal": "crying Pixar cat sitting at laptop desk"},
    {"topic": "Code worked locally but failed in production", "animal": "shocked 3D Pixar dog with glasses"}
]

BG_MUSIC_URLS = [
    "https://actions.google.com/sounds/v1/cartoon/cartoon_boing.ogg",
    "https://actions.google.com/sounds/v1/cartoon/clown_horn.ogg",
    "https://actions.google.com/sounds/v1/cartoon/pop.ogg"
]

def get_script():
    client = genai.Client(api_key=GEMINI_API_KEY)
    preset = random.choice(VIRAL_MEME_PRESETS)
    
    prompt = f"""
    Write a short, highly relatable IT meme voiceover script based on this joke format:
    TOPIC: {preset['topic']}.
    ANIMAL CHARACTER: {preset['animal']}.
    
    Guidelines:
    - Keep it under 12-15 seconds.
    - Highly relatable, hilarious developer life moment.
    - End with: "Subscribe to Tech Humor Lab for daily IT laughs!"
    
    Return ONLY a JSON object:
    {{
      "text": "The spoken voiceover text without emojis",
      "image_prompts": [
        "A 3D Pixar style cute fluffy cat wearing a hoodie sitting at laptop computer in programmer office, highly detailed 8k render, octane render", 
        "A 3D Pixar style cute dog looking shocked and stressed at computer screen with code, vibrant lighting, highly detailed", 
        "A 3D Pixar style cat facepalm holding head at desk near laptop, funny meme expression, 8k"
      ],
      "title": "{preset['topic']} 💀 #shorts #ithumor #programming #devlife #pixar",
      "tags": ["TechHumor", "ProgrammingMemes", "Coding", "DeveloperLife", "Shorts", "Pixar", "Animation"]
    }}
    """
    
    for attempt in range(5):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            raw_text = response.text.strip()
            # Безопасная избыточная очистка от форматирования markdown
            clean_text = raw_text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_text)
        except Exception as e:
            print(f"⚠️ Попытка {attempt + 1} не удалась ({e}). Ждем 15 сек...")
            time.sleep(15)
            
    raise Exception("❌ Ошибка Gemini.")

async def create_audio(text):
    voice = "en-US-EricNeural" 
    communicate = edge_tts.Communicate(text, voice, rate="+20%", pitch="+6Hz")
    await communicate.save("audio.mp3")

def download_bg_music():
    music_url = random.choice(BG_MUSIC_URLS)
    try:
        res = requests.get(music_url)
        with open("bg_music.ogg", "wb") as f:
            f.write(res.content)
        return "bg_music.ogg"
    except Exception as e:
        print(f"⚠️ Не удалось скачать фоновую музыку: {e}")
        return None

def generate_pixar_images(prompts):
    downloaded_files = []
    for idx, raw_prompt in enumerate(prompts[:3]):
        full_prompt = f"{raw_prompt}, 3D Disney Pixar animation style, cute character, vibrant cinematic lighting, highly detailed 8k"
        encoded_prompt = urllib.parse.quote(full_prompt)
        
        seed = random.randint(1, 99999)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&seed={seed}&nologo=true"
        
        file_name = f"bg_{idx}.jpg"
        print(f"🎨 Генерация Pixar-картинки {idx + 1}/3...")
        
        res = requests.get(image_url)
        if res.status_code == 200:
            with open(file_name, "wb") as f:
                f.write(res.content)
            downloaded_files.append(file_name)
        else:
            res = requests.get("https://picsum.photos/1080/1920")
            with open(file_name, "wb") as f:
                f.write(res.content)
            downloaded_files.append(file_name)
            
    return downloaded_files

def split_text_into_chunks(text, words_per_chunk=3):
    words = text.split()
    chunks = []
    for i in range(0, len(words), words_per_chunk):
        chunk = " ".join(words[i:i + words_per_chunk])
        chunks.append(chunk)
    return chunks

def build_video(script_text, image_files, bg_music_file=None):
    voice_audio = AudioFileClip("audio.mp3")
    duration = voice_audio.duration
    clip_duration = duration / len(image_files)

    clips = []
    for file in image_files:
        clip = ImageClip(file).set_duration(clip_duration).resize(width=1080)
        clip_animated = clip.resize(lambda t: 1 + 0.05 * t).set_position(('center', 'center'))
        clips.append(clip_animated)

    video_bg = concatenate_videoclips(clips, method="compose").set_duration(duration)

    chunks = split_text_into_chunks(script_text, words_per_chunk=3)
    chunk_duration = duration / len(chunks)
    
    text_clips = []
    for idx, chunk in enumerate(chunks):
        start_time = idx * chunk_duration
        try:
            txt_clip = (TextClip(
                            txt=chunk.upper(), 
                            fontsize=52, 
                            color='yellow', 
                            bg_color='rgba(0,0,0,0.75)',
                            font='DejaVu-Sans-Bold',
                            method='caption',
                            size=(int(1080 * 0.82), None)
                        )
                        .set_start(start_time)
                        .set_duration(chunk_duration)
                        .set_position(('center', 1280)))
            text_clips.append(txt_clip)
        except Exception as e:
            print(f"⚠️ Ошибка на фрагменте субтитров '{chunk}': {e}")

    final_clip = CompositeVideoClip([video_bg] + text_clips, size=(1080, 1920))

    audio_tracks = [voice_audio]
    if bg_music_file and os.path.exists(bg_music_file):
        try:
            bg_audio = AudioFileClip(bg_music_file).volumex(0.15)
            if bg_audio.duration < duration:
                bg_audio = bg_audio.loop(duration=duration)
            else:
                bg_audio = bg_audio.subclip(0, duration)
            audio_tracks.append(bg_audio)
        except Exception as e:
            print(f"⚠️ Ошибка наложения музыки: {e}")

    final_audio = CompositeAudioClip(audio_tracks)
    final_clip = final_clip.set_audio(final_audio)

    final_clip.write_videofile("final_short.mp4", fps=24, codec="libx264", audio_codec="aac")
    voice_audio.close()

def upload_to_youtube(metadata):
    from google.oauth2.credentials import Credentials
    
    creds = Credentials.from_authorized_user_file('token.json', ["https://www.googleapis.com/auth/youtube.upload"])
    youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)

    description_text = (
        f"{metadata['text']}\n\n"
        f"💀 Relatable IT memes and dev life moments.\n"
        f"🔔 Subscribe to Tech Humor Lab for daily laughs!\n\n"
        f"#shorts #ithumor #programming #coding #tech #animation #cats #pixar"
    )

    body = {
        'snippet': {
            'title': metadata['title'],
            'description': description_text,
            'tags': metadata['tags'],
            'categoryId': '23'
        },
        'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}
    }

    media = MediaFileUpload("final_short.mp4", mimetype="video/mp4", resumable=False)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    print(f"✅ МЕМ-РОЛИК ОПУБЛИКОВАН! ID: {response.get('id')}")

if __name__ == "__main__":
    print("1. Генерируем IT-шутку...")
    data = get_script()
    print("2. Озвучиваем текст и скачиваем фоновый звук...")
    asyncio.run(create_audio(data['text']))
    bg_music = download_bg_music()
    print("3. Генерируем 3 уникальные Pixar-картинки через ИИ...")
    images = generate_pixar_images(data.get('image_prompts', [
        "A 3D Pixar style cat programmer", 
        "A 3D Pixar style dog laptop", 
        "A 3D Pixar cat desk"
    ]))
    print("4. Собираем ролик с фоновой музыкой и субтитрами на 2/3 экрана...")
    build_video(data['text'], images, bg_music)
    print("5. Публикуем на YouTube...")
    upload_to_youtube(data)
