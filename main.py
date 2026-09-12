import os
import re
import json
import time
import random
import asyncio
import textwrap
import requests
from google import genai
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip
import google_auth_oauthlib.flow
import googleapiclient.discovery
from googleapiclient.http import MediaFileUpload

# Восстановление секретов
if not os.path.exists('client_secret.json'):
    with open('client_secret.json', 'w') as f:
        f.write(os.getenv('CLIENT_SECRET_JSON', ''))

if not os.path.exists('token.json'):
    with open('token.json', 'w') as f:
        f.write(os.getenv('YOUTUBE_TOKEN', ''))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

HUMOR_TOPICS = [
    "junior dev deleting production database", "fixing bug creates 10 new bugs",
    "senior dev code review feedback", "trying to center a div with CSS",
    "deploying unverified code on Friday 5 PM", "StackOverflow answer from 2011",
    "client asking for a quick small change", "AI writing code with confidence"
]

# Резервные сценарии на случай полного исчерпания суточной квоты Gemini
FALLBACK_SCRIPTS = [
    {
        "text": "When you fix a typo and production goes down immediately.",
        "image_query": "stressed programmer computer",
        "title": "IT Life Be Like... 💀 #shorts #ithumor #tech #programming",
        "tags": ["TechHumor", "ProgrammingMemes", "Coding", "DeveloperLife", "Shorts"]
    },
    {
        "text": "Deploying unverified code on Friday at 5 PM. What could possibly go wrong?",
        "image_query": "funny cat laptop shock",
        "title": "Friday Deployment Be Like... 💀 #shorts #ithumor #tech #programming",
        "tags": ["TechHumor", "ProgrammingMemes", "Coding", "DeveloperLife", "Shorts"]
    },
    {
        "text": "One bug fixed, ten new features created for the QA team.",
        "image_query": "programmer disaster face",
        "title": "Bug Fixing Logic... 💀 #shorts #ithumor #tech #programming",
        "tags": ["TechHumor", "ProgrammingMemes", "Coding", "DeveloperLife", "Shorts"]
    }
]

def get_script():
    client = genai.Client(api_key=GEMINI_API_KEY)
    selected_topic = random.choice(HUMOR_TOPICS)
    
    prompt = f"""
    Write a hilarious, relatable IT meme script.
    TOPIC: {selected_topic}.
    Random seed: {random.randint(1000, 9999)}
    
    Return ONLY a JSON object:
    {{
      "text": "When you fix a typo and production goes down immediately.",
      "image_query": "funny cat computer OR stressed programmer OR disaster face",
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
            # Вытягиваем точное время ожидания от Google (например, retryDelay: '42s')
            match = re.search(r"retryDelay': '(\d+)s'", err_msg)
            wait_time = int(match.group(1)) + 2 if match else 35
            print(f"⚠️ Ошибка Gemini (429/Квота). Попытка {attempt + 1}/5. Ждём {wait_time} сек...")
            time.sleep(wait_time)
            
    print("⚠️ Квота Gemini исчерпана. Используем резервный IT-мем...")
    return random.choice(FALLBACK_SCRIPTS)

async def create_audio(text):
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save("audio.mp3")

def download_pexels_image(query):
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/v1/search?query={query}&per_page=15&orientation=portrait"
    res = requests.get(url, headers=headers).json()
    
    photos = res.get("photos", [])
    if not photos:
        res = requests.get("https://api.pexels.com/v1/search?query=programmer&per_page=10&orientation=portrait", headers=headers).json()
        photos = res.get("photos", [])

    selected = random.choice(photos)
    image_url = selected["src"]["large2x"]
    
    with open("meme_bg.jpg", "wb") as f:
        f.write(requests.get(image_url).content)

def build_video(script_text):
    audio = AudioFileClip("audio.mp3")
    duration = audio.duration
    target_w, target_h = 1080, 1920

    # Пропорциональный Crop-to-Fill в PIL (заполняем 9:16 без растяжения)
    img = Image.open("meme_bg.jpg").convert("RGB")
    orig_w, orig_h = img.size

    scale = max(target_w / orig_w, target_h / orig_h)
    new_w, new_h = int(orig_w * scale), int(orig_h * scale)
    img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    bg_canvas = img_resized.crop((left, top, left + target_w, top + target_h))

    # Рендерим субтитры прямо на картинке через PIL
    draw = ImageDraw.Draw(bg_canvas)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
    except:
        font = ImageFont.load_default()

    wrapped_lines = textwrap.wrap(script_text, width=22)
    line_height = 70
    y_text = int(target_h * 0.32)

    for line in wrapped_lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (target_w - w) / 2

        # Чёрная обводка
        for adj in [(-3,0), (3,0), (0,-3), (0,3), (-3,-3), (3,3), (-3,3), (3,-3)]:
            draw.text((x + adj[0], y_text + adj[1]), line, font=font, fill="black")

        # Жёлтый текст
        draw.text((x, y_text), line, font=font, fill="yellow")
        y_text += line_height

    bg_canvas.save("final_frame.jpg")

    # Анимация Zoom-In и сборка
    img_clip = ImageClip("final_frame.jpg").set_duration(duration)
    img_animated = img_clip.resize(lambda t: 1 + 0.04 * t).set_position(('center', 'center'))

    final_clip = CompositeVideoClip([img_animated], size=(target_w, target_h))
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
    print("3. Ищем мемный визуал...")
    download_pexels_image(data['image_query'])
    print("4. Собираем динамический ролик с Zoom-эффектом...")
    build_video(data['text'])
    print("5. Публикуем на YouTube...")
    upload_to_youtube(data)
