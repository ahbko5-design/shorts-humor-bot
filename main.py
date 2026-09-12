import os
import json
import time
import random
import requests
import asyncio
from google import genai
import edge_tts

try:
    from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip, concatenate_videoclips
except ImportError:
    from moviepy.video.VideoClip import ImageClip
    from moviepy.audio.io.AudioFileClip import AudioFileClip
    from moviepy.video.VideoClip import TextClip
    from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
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
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

# Популярные золотые шаблоны IT-шуток
VIRAL_MEME_PRESETS = [
    {"topic": "Senior Dev vs Junior Dev in Code Review", "query": "funny dog, programmer stress, facepalm"},
    {"topic": "Deploying on Friday 5 PM", "query": "fire disaster, shocked cat, exploding building"},
    {"topic": "Fixing one bug and creating 10 new bugs", "query": "confused meme, hydra, chaos computer"},
    {"topic": "CSS centering a div struggle", "query": "crazy reaction, screaming face, broken computer"},
    {"topic": "Client asking for a quick small change", "query": "crying cat, fake smile, disaster face"},
    {"topic": "Code worked in local environment but failed in production", "query": "shocked face, clown, panicking man"}
]

def get_script():
    client = genai.Client(api_key=GEMINI_API_KEY)
    preset = random.choice(VIRAL_MEME_PRESETS)
    
    prompt = f"""
    Write a short, highly relatable IT meme voiceover script based on this classic joke format:
    TOPIC: {preset['topic']}.
    
    Guidelines:
    - Keep it under 12-15 seconds.
    - Highly relatable, hilarious developer life moment.
    - End with: "Subscribe to Tech Humor Lab for daily IT laughs!"
    
    Return ONLY a JSON object:
    {{
      "text": "The spoken voiceover text without emojis",
      "image_queries": ["funny programmer", "shocked reaction", "crying face"],
      "title": "{preset['topic']} 💀 #shorts #ithumor #programming #devlife",
      "tags": ["TechHumor", "ProgrammingMemes", "Coding", "DeveloperLife", "Shorts"]
    }}
    """
    
    for attempt in range(5):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            raw_text = response.text.strip()
            if "```" in raw_text:
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
            return json.loads(raw_text.strip())
        except Exception as e:
            print(f"⚠️ Попытка {attempt + 1} не удалась ({e}). Ждем 15 сек...")
            time.sleep(15)
            
    raise Exception("❌ Ошибка Gemini.")

async def create_audio(text):
    # Экспрессивный быстрый тон
    voice = "en-US-EricNeural" 
    communicate = edge_tts.Communicate(text, voice, rate="+20%", pitch="+6Hz")
    await communicate.save("audio.mp3")

def download_images(queries):
    headers = {"Authorization": PEXELS_API_KEY}
    downloaded_files = []
    
    for idx, query in enumerate(queries[:3]):
        url = f"https://api.pexels.com/v1/search?query={query}&per_page=10&orientation=portrait"
        res = requests.get(url, headers=headers).json()
        photos = res.get("photos", [])
        
        if photos:
            img_url = random.choice(photos)["src"]["large2x"]
        else:
            img_url = "https://images.pexels.com/photos/1181675/pexels-photo-1181675.jpeg"
            
        file_name = f"bg_{idx}.jpg"
        with open(file_name, "wb") as f:
            f.write(requests.get(img_url).content)
        downloaded_files.append(file_name)
        
    return downloaded_files

def build_video(script_text, image_files):
    audio = AudioFileClip("audio.mp3")
    duration = audio.duration
    clip_duration = duration / len(image_files)

    clips = []
    for file in image_files:
        clip = ImageClip(file).set_duration(clip_duration).resize(width=1080)
        # Накладываем динамический Zoom
        clip_animated = clip.resize(lambda t: 1 + 0.05 * t).set_position(('center', 'center'))
        clips.append(clip_animated)

    # Склеиваем слайдовую презентацию из 3 кадров
    video_bg = concatenate_videoclips(clips, method="compose").set_duration(duration)

    # Стабильный способ вывода субтитров с черной контрастной подложкой
    try:
        txt_clip = (TextClip(
                        txt=script_text, 
                        fontsize=40, 
                        color='yellow', 
                        bg_color='rgba(0,0,0,0.6)',
                        font='DejaVu-Sans-Bold',
                        method='caption',
                        size=(int(1080 * 0.85), None)
                    )
                    .set_position(('center', 1400))
                    .set_duration(duration))

        final_clip = CompositeVideoClip([video_bg, txt_clip], size=(1080, 1920))
    except Exception as e:
        print(f"❌ Ошибка вывода субтитров: {e}")
        final_clip = CompositeVideoClip([video_bg], size=(1080, 1920))

    final_clip = final_clip.set_audio(audio)
    final_clip.write_videofile("final_short.mp4", fps=24, codec="libx264", audio_codec="aac")
    audio.close()

def upload_to_youtube(metadata):
    from google.oauth2.credentials import Credentials
    
    creds = Credentials.from_authorized_user_file('token.json', ["https://www.googleapis.com/auth/youtube.upload"])
    youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)

    description_text = (
        f"{metadata['text']}\n\n"
        f"💀 Relatable IT memes and dev life moments.\n"
        f"🔔 Subscribe to Tech Humor Lab for daily laughs!\n\n"
        f"#shorts #ithumor #programming #coding #tech"
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
    print("1. Генерируем классическую IT-шутку...")
    data = get_script()
    print("2. Озвучиваем быстрой динамичной речью...")
    asyncio.run(create_audio(data['text']))
    print("3. Скачиваем 3 динамических визуальных кадра...")
    images = download_images(data.get('image_queries', ["programmer", "meme", "funny"]))
    print("4. Собираем мульти-кадровое видео с титрами...")
    build_video(data['text'], images)
    print("5. Опубликовать на YouTube...")
    upload_to_youtube(data)
