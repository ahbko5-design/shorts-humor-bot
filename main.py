import os
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

# 1. Восстановление секретов и файлов авторизации
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

def get_script():
    client = genai.Client(api_key=GEMINI_API_KEY)
    selected_topic = random.choice(HUMOR_TOPICS)
    
    prompt = f"""
    Write a hilarious, relatable IT meme script.
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
            raw_text = response.text.strip()
            raw_text = raw_text.replace("```json", "").replace("```", "").strip()
            return json.loads(raw_text)
        except Exception as e:
            print(f"⚠️ Попытка {attempt + 1} не удалась ({e}). Ждем 15 сек...")
            time.sleep(15)
            
    raise Exception("❌ Ошибка при генерации через Gemini.")

async def create_audio(text):
    voice = "en-US-EricNeural" 
    communicate = edge_tts.Communicate(text, voice, rate="+15%", pitch="+5Hz")
    await communicate.save("audio.mp3")

def download_pexels_image(query):
    headers = {"Authorization": PEXELS_API_KEY}
    random_page = random.randint(1, 3)
    url = f"https://api.pexels.com/v1/search?query={query}&per_page=15&page={random_page}&orientation=portrait"
    res = requests.get(url, headers=headers).json()
    
    photos = res.get("photos", [])
    if not photos:
        res = requests.get("https://api.pexels.com/v1/search?query=programmer&per_page=10&orientation=portrait", headers=headers).json()
        photos = res.get("photos", [])

    selected = random.choice(photos)
    image_url = selected["src"]["large2x"]
    
    with open("meme_bg.jpg", "wb") as f:
        f.write(requests.get(image_url).content)
    print("📸 Мемная картинка успешно загружена!")

def build_video(script_text):
    audio = AudioFileClip("audio.mp3")
    duration = audio.duration
    target_w, target_h = 1080, 1920

    # 1. Загружаем картинку и делаем идеальный вертикальный холст 9:16 без растягивания
    img = Image.open("meme_bg.jpg").convert("RGB")
    img_w, img_h = img.size
    
    scale = max(target_w / img_w, target_h / img_h)
    new_w, new_h = int(img_w * scale), int(img_h * scale)
    
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    background = Image.new("RGB", (target_w, target_h), (0, 0, 0))
    left = (target_w - new_w) // 2
    top = (target_h - new_h) // 2
    background.paste(img, (left, top))

    # 2. Рендерим текст поверх вертикального кадра через PIL
    draw = ImageDraw.Draw(background)
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 55)
    except:
        font = ImageFont.load_default()

    wrapped_lines = textwrap.wrap(script_text, width=22)
    line_height = 75
    y_text = int(target_h * 0.25)

    for line in wrapped_lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (target_w - w) / 2
        
        # Черная обводка для читаемости текста
        for adj in [(-3,0), (3,0), (0,-3), (0,3), (-3,-3), (3,3), (-3,3), (3,-3)]:
            draw.text((x + adj[0], y_text + adj[1]), line, font=font, fill="black")
        
        # Основной желтый текст
        draw.text((x, y_text), line, font=font, fill="yellow")
        y_text += line_height

    final_frame_path = "final_frame.jpg"
    background.save(final_frame_path)

    # 3. Собираем видео с анимацией Zoom-In
    img_clip = ImageClip(final_frame_path).set_duration(duration)
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
    print("3. Скачиваем картинку...")
    download_pexels_image(data['image_query'])
    print("4. Собираем вертикальный ролик с текстом и зумом...")
    build_video(data['text'])
    print("5. Публикуем на YouTube...")
    upload_to_youtube(data)
