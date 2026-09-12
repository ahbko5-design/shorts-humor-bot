import os
import re
import json
import time
import random
import asyncio
import textwrap
import requests
import numpy as np
from google import genai
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, AudioFileClip, VideoClip, CompositeVideoClip
import google_auth_oauthlib.flow
import googleapiclient.discovery
from googleapiclient.http import MediaFileUpload

# 1. Восстановление секретов и авторизации
if not os.path.exists('client_secret.json'):
    with open('client_secret.json', 'w') as f:
        f.write(os.getenv('CLIENT_SECRET_JSON', ''))

if not os.path.exists('token.json'):
    with open('token.json', 'w') as f:
        f.write(os.getenv('YOUTUBE_TOKEN', ''))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

HUMOR_TOPICS = [
    "junior dev deleting production database", 
    "fixing bug creates 10 new bugs",
    "senior dev code review feedback", 
    "trying to center a div with CSS",
    "deploying unverified code on Friday 5 PM", 
    "StackOverflow answer saving the day",
    "client asking for a quick small change", 
    "AI writing code with full confidence"
]

FALLBACK_SCRIPTS = [
    {
        "text": "When you fix a simple typo and production goes down immediately. Subscribe to Tech Humor Lab for daily IT laughs!",
        "image_query": "funny cat computer OR stressed programmer",
        "title": "IT Life Be Like... 💀 #shorts #ithumor #tech #programming",
        "tags": ["TechHumor", "ProgrammingMemes", "Coding", "DeveloperLife", "Shorts"]
    },
    {
        "text": "Deploying unverified code on Friday at 5 PM. What could go wrong? Subscribe to Tech Humor Lab for daily IT laughs!",
        "image_query": "disaster face OR shock programmer",
        "title": "Friday Deployment Be Like... 💀 #shorts #ithumor #tech #programming",
        "tags": ["TechHumor", "ProgrammingMemes", "Coding", "DeveloperLife", "Shorts"]
    }
]

def get_script():
    client = genai.Client(api_key=GEMINI_API_KEY)
    selected_topic = random.choice(HUMOR_TOPICS)
    
    prompt = f"""
    Write a short, hilarious, punchy IT meme script (2 sentences max).
    TOPIC: {selected_topic}.
    Random seed: {random.randint(1000, 9999)}
    
    Voiceover guidelines:
    - Sarcastic, fast-paced developer moment.
    - END WITH: "Subscribe to Tech Humor Lab for daily IT laughs!"
    
    Return ONLY a JSON object:
    {{
      "text": "The full spoken text of the video without markdown or emojis",
      "image_query": "funny cat computer OR stressed programmer OR disaster face OR shocked face OR hacker",
      "title": "IT Life Be Like... 💀 #shorts #ithumor #tech #programming",
      "tags": ["TechHumor", "ProgrammingMemes", "Coding", "DeveloperLife", "Shorts"]
    }}
    """
    
    for attempt in range(5):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            raw = response.text
            start = raw.find('{')
            end = raw.rfind('}') + 1
            return json.loads(raw[start:end])
        except Exception as e:
            err_msg = str(e)
            match = re.search(r"retryDelay': '(\d+)s'", err_msg)
            wait_time = int(match.group(1)) + 2 if match else 35
            print(f"⚠️ Задержка Gemini (429). Попытка {attempt + 1}/5. Ждём {wait_time} сек...")
            time.sleep(wait_time)
            
    print("⚠️ Квота Gemini исчерпана. Берем резервный сценарий...")
    return random.choice(FALLBACK_SCRIPTS)

async def create_audio(text):
    voice = "en-US-EricNeural" 
    communicate = edge_tts.Communicate(text, voice, rate="+15%", pitch="+5Hz")
    await communicate.save("audio.mp3")

def download_pexels_image(query):
    headers = {"Authorization": PEXELS_API_KEY}
    random_page = random.randint(1, 8)
    url = f"https://api.pexels.com/v1/search?query={query}&per_page=15&page={random_page}&orientation=portrait"
    res = requests.get(url, headers=headers).json()
    
    photos = res.get("photos", [])
    if not photos:
        random_page = random.randint(1, 5)
        res = requests.get(f"https://api.pexels.com/v1/search?query=programmer&per_page=15&page={random_page}&orientation=portrait", headers=headers).json()
        photos = res.get("photos", [])

    selected = random.choice(photos)
    image_url = selected["src"]["large2x"]
    
    with open("meme_bg.jpg", "wb") as f:
        f.write(requests.get(image_url).content)
    print("📸 Новая случайная картинка с Pexels скачана!")

def prepare_vertical_background():
    target_w, target_h = 1080, 1920
    img = Image.open("meme_bg.jpg").convert("RGB")
    orig_w, orig_h = img.size

    scale = max(target_w / orig_w, target_h / orig_h)
    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)

    img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    cropped_img = img_resized.crop((left, top, left + target_w, top + target_h))
    
    cropped_img.save("clean_bg.jpg")

def build_video(script_text):
    audio = AudioFileClip("audio.mp3")
    total_duration = audio.duration
    target_w, target_h = 1080, 1920

    prepare_vertical_background()

    # Фоновый клип с плавной анимацией Zoom-In
    bg_clip = ImageClip("clean_bg.jpg").set_duration(total_duration)
    bg_animated = bg_clip.resize(lambda t: 1 + 0.04 * (t / total_duration)).set_position(('center', 'center'))

    # Разбиение текста на короткие фразы (по 3-4 слова) для бегущих субтитров
    words = script_text.split()
    chunks = []
    current_chunk = []
    for word in words:
        current_chunk.append(word)
        if len(current_chunk) >= 4:
            chunks.append(" ".join(current_chunk))
            current_chunk = []
    if current_chunk:
        chunks.append(" ".join(current_chunk))

    chunk_duration = total_duration / max(len(chunks), 1)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
    except:
        font = ImageFont.load_default()

    # Отрисовка текста на видимом клипе
    def make_caption_frame(t):
        chunk_idx = min(int(t / chunk_duration), len(chunks) - 1)
        current_text = chunks[chunk_idx]

        txt_image = Image.new("RGB", (target_w, target_h), (0, 0, 0))
        draw = ImageDraw.Draw(txt_image)

        wrapped = textwrap.wrap(current_text, width=18)
        y_text = int(target_h * 0.38)

        for line in wrapped:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            x = (target_w - w) / 2

            for adj in [(-4,0), (4,0), (0,-4), (0,4), (-4,-4), (4,4), (-4,4), (4,-4)]:
                draw.text((x + adj[0], y_text + adj[1]), line, font=font, fill="black")

            draw.text((x, y_text), line, font=font, fill="yellow")
            y_text += 75

        return np.array(txt_image)

    # Отрисовка маски прозрачности
    def make_mask_frame(t):
        chunk_idx = min(int(t / chunk_duration), len(chunks) - 1)
        current_text = chunks[chunk_idx]

        mask_image = Image.new("L", (target_w, target_h), 0)
        draw = ImageDraw.Draw(mask_image)

        wrapped = textwrap.wrap(current_text, width=18)
        y_text = int(target_h * 0.38)

        for line in wrapped:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            x = (target_w - w) / 2

            for adj in [(-4,0), (4,0), (0,-4), (0,4), (-4,-4), (4,4), (-4,4), (4,-4)]:
                draw.text((x + adj[0], y_text + adj[1]), line, font=font, fill=255)

            draw.text((x, y_text), line, font=font, fill=255)
            y_text += 75

        return np.array(mask_image) / 255.0

    caption_clip = VideoClip(make_caption_frame, duration=total_duration)
    mask_clip = VideoClip(make_mask_frame, ismask=True, duration=total_duration)
    caption_clip = caption_clip.set_mask(mask_clip)

    final_clip = CompositeVideoClip([bg_animated, caption_clip], size=(target_w, target_h))
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
    print("1. Генерируем IT-мем...")
    data = get_script()
    print("2. Озвучиваем текст...")
    asyncio.run(create_audio(data['text']))
    print("3. Ищем случайный визуал с Pexels...")
    download_pexels_image(data['image_query'])
    print("4. Собираем 9:16 видео с бегущими субтитрами...")
    build_video(data['text'])
    print("5. Публикуем на YouTube...")
    upload_to_youtube(data)
