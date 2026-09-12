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

VIRAL_MEME_PRESETS = [
    {"topic": "Senior Dev vs Junior Dev in Code Review", "query": "funny cat computer, cute dog programmer, facepalm cat"},
    {"topic": "Deploying code on Friday at 5 PM", "query": "cat chaos computer, scared dog, disaster cat"},
    {"topic": "Fixing 1 bug creates 10 new bugs", "query": "confused cat, dog working laptop, stressed cat"},
    {"topic": "Trying to center a div with CSS", "query": "screaming cat, funny dog office, crazy cat laptop"},
    {"topic": "Client asking for a quick small change", "query": "crying cat, fake smile dog, funny cat face"},
    {"topic": "Code worked locally but failed in production", "query": "shocked cat, dog wearing glasses computer, facepalm dog"}
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
      "image_queries": [
        "pixar style cat sitting at laptop computer", 
        "funny 3d dog programmer stressed office", 
        "cute cat facepalm computer desk"
      ],
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
    voice = "en-US-EricNeural" 
    communicate = edge_tts.Communicate(text, voice, rate="+20%", pitch="+6Hz")
    await communicate.save("audio.mp3")

def download_images(queries):
    headers = {"Authorization": PEXELS_API_KEY}
    downloaded_files = []
    
    # Резервные поисковые запросы для животных в стиле Pixar/людей
    fallback_queries = [
        "funny cat computer", 
        "cute dog laptop office", 
        "funny pet wearing hoodie desk"
    ]
    
    for idx, query in enumerate(queries[:3]):
        url = f"https://api.pexels.com/v1/search?query={query}&per_page=15&orientation=portrait"
        res = requests.get(url, headers=headers).json()
        photos = res.get("photos", [])
        
        # Если оригинальный запрос сложный, пробуем резервный
        if not photos:
            fallback = fallback_queries[idx % len(fallback_queries)]
            url = f"https://api.pexels.com/v1/search?query={fallback}&per_page=15&orientation=portrait"
            res = requests.get(url, headers=headers).json()
            photos = res.get("photos", [])
            
        if photos:
            img_url = random.choice(photos)["src"]["large2x"]
        else:
            img_url = "https://images.pexels.com/photos/1170986/pexels-photo-1170986.jpeg" # Запасной пушистый кот
            
        file_name = f"bg_{idx}.jpg"
        with open(file_name, "wb") as f:
            f.write(requests.get(img_url).content)
        downloaded_files.append(file_name)
        
    return downloaded_files

def split_text_into_chunks(text, words_per_chunk=3):
    """Разбивает текст на короткие фразы по 2-3 слова для динамичных субтитров"""
    words = text.split()
    chunks = []
    for i in range(0, len(words), words_per_chunk):
        chunk = " ".join(words[i:i + words_per_chunk])
        chunks.append(chunk)
    return chunks

def build_video(script_text, image_files):
    audio = AudioFileClip("audio.mp3")
    duration = audio.duration
    clip_duration = duration / len(image_files)

    # 1. Создаем динамическое видео из сменяющихся картинок животных с Zoom-эффектом
    clips = []
    for file in image_files:
        clip = ImageClip(file).set_duration(clip_duration).resize(width=1080)
        clip_animated = clip.resize(lambda t: 1 + 0.05 * t).set_position(('center', 'center'))
        clips.append(clip_animated)

    video_bg = concatenate_videoclips(clips, method="compose").set_duration(duration)

    # 2. Динамические короткие субтитры по 2-3 слова в безопасной зоне
    chunks = split_text_into_chunks(script_text, words_per_chunk=3)
    chunk_duration = duration / len(chunks)
    
    text_clips = []
    for idx, chunk in enumerate(chunks):
        start_time = idx * chunk_duration
        try:
            txt_clip = (TextClip(
                            txt=chunk.upper(), 
                            fontsize=55, 
                            color='yellow', 
                            bg_color='rgba(0,0,0,0.7)',
                            font='DejaVu-Sans-Bold',
                            method='caption',
                            size=(int(1080 * 0.8), None)
                        )
                        .set_start(start_time)
                        .set_duration(chunk_duration)
                        .set_position(('center', 650)))
            text_clips.append(txt_clip)
        except Exception as e:
            print(f"⚠️ Ошибка на фрагменте субтитров '{chunk}': {e}")

    final_clip = CompositeVideoClip([video_bg] + text_clips, size=(1080, 1920))
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
        f"#shorts #ithumor #programming #coding #tech #funnycats #dogs"
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
    print("2. Озвучиваем текст...")
    asyncio.run(create_audio(data['text']))
    print("3. Ищем забавных животных в роли IT-шников...")
    images = download_images(data.get('image_queries', [
        "pixar style cat computer", 
        "funny dog programmer", 
        "cute cat laptop desk"
    ]))
    print("4. Собираем динамичный ролик с живыми субтитрами...")
    build_video(data['text'], images)
    print("5. Публикуем на YouTube...")
    upload_to_youtube(data)
