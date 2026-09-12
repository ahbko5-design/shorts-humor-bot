import os
import json
import time
import random
import requests
import asyncio
from google import genai
import edge_tts
from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip
import google_auth_oauthlib.flow
import googleapiclient.discovery
from googleapiclient.http import MediaFileUpload

# 1. Восстановление секретов
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
    - Sarcastic, fast-paced, relatable developer moment.
    - END WITH: "Subscribe to Tech Humor Lab for daily IT laughs!"
    
    Return ONLY a JSON object:
    {{
      "text": "The full spoken text of the video without markdown or emojis",
      "image_query": "funny cat computer OR stressed programmer OR disaster face OR shocked face",
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
            if "```" in raw_text:
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
            return json.loads(raw_text.strip())
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

def build_video(script_text):
    audio = AudioFileClip("audio.mp3")
    duration = audio.duration

    # Создаем клип с Zoom-эффектом
    img_clip = ImageClip("meme_bg.jpg").set_duration(duration)
    img_animated = img_clip.resize(lambda t: 1 + 0.04 * t).set_position(('center', 'center'))

    # Накладываем желтые субтитры по центру
    try:
        txt_clip = (TextClip(
                        txt=script_text, 
                        fontsize=42, 
                        color='yellow', 
                        font='DejaVu-Sans-Bold',
                        stroke_color='black',
                        stroke_width=3,
                        method='caption',
                        size=(int(1080 * 0.85), None)
                    )
                    .set_position(('center', 'center'))
                    .set_duration(duration))

        final_clip = CompositeVideoClip([img_animated, txt_clip], size=(1080, 1920))
    except Exception as e:
        print(f"⚠️ Ошибка вывода субтитров: {e}. Монтируем без текста.")
        final_clip = CompositeVideoClip([img_animated], size=(1080, 1920))

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
    print("2. Озвучиваем текст с динамическим тоном...")
    asyncio.run(create_audio(data['text']))
    print("3. Ищем мемную реакцию на Pexels...")
    download_pexels_image(data['image_query'])
    print("4. Собираем видео с Zoom-эффектом и субтитрами...")
    build_video(data['text'])
    print("5. Загружаем на YouTube...")
    upload_to_youtube(data)
