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
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
import google_auth_oauthlib.flow
import googleapiclient.discovery
from googleapiclient.http import MediaFileUpload

if not os.path.exists('client_secret.json'):
    with open('client_secret.json', 'w') as f:
        f.write(os.getenv('CLIENT_SECRET_JSON', ''))

if not os.path.exists('token.json'):
    with open('token.json', 'w') as f:
        f.write(os.getenv('YOUTUBE_TOKEN', ''))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

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
    Write a short, hilarious, punchy IT meme script (maximum 2 sentences).
    TOPIC: {selected_topic}.
    
    Voiceover guidelines:
    - Sarcastic, fast-paced developer moment.
    - Keep it concise so captions fit nicely.
    - END WITH: "Classic developer life!"
    
    Return ONLY a JSON object:
    {{
      "text": "Short spoken punchline here",
      "image_prompt": "3D Pixar animation character, funny programmer reacting to computer error, highly detailed 3D render",
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
            raw_text = response.text.strip().replace("```json", "").replace("```", "").strip()
            return json.loads(raw_text)
        except Exception as e:
            print(f"⚠️ Попытка {attempt + 1} не удалась ({e}). Ждем 10 сек...")
            time.sleep(10)
            
    raise Exception("❌ Ошибка от Gemini.")

async def create_audio(text):
    voice = "en-US-EricNeural" 
    communicate = edge_tts.Communicate(text, voice, rate="+15%", pitch="+5Hz")
    await communicate.save("audio.mp3")

def generate_ai_image(image_prompt):
    # Прямой генератор Flux.1 / SDXL с ПРИНУДИТЕЛЬНЫМ вертикальным форматом 9:16 (768x1344)
    prompt_formatted = requests.utils.quote(f"{image_prompt}, 3d pixar style, portrait orientation, 9:16 aspect ratio, highly detailed")
    
    # Запрос напрямую на нейросеть с поддержкой соотношения сторон
    url = f"https://image.pollinations.ai/prompt/{prompt_formatted}?model=flux&width=768&height=1344&nologo=true&seed={random.randint(1, 100000)}"
    
    res = requests.get(url)
    with open("meme_bg.jpg", "wb") as f:
        f.write(res.content)
    print("🎨 Вертикальная ИИ-картинка (9:16) успешно сгенерирована!")

def build_video(script_text):
    audio = AudioFileClip("audio.mp3")
    total_duration = audio.duration
    target_w, target_h = 1080, 1920

    # Загружаем ИЗНАЧАЛЬНО вертикальное фото и просто приводим к разрешению холста 1080x1920
    img_base = Image.open("meme_bg.jpg").convert("RGB")
    bg_canvas = img_base.resize((target_w, target_h), Image.Resampling.LANCZOS)

    # Разбиваем текст на бегущие короткие строчки (по 3-4 слова)
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
    clips = []

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 65)
    except:
        font = ImageFont.load_default()

    for i, chunk in enumerate(chunks):
        frame_img = bg_canvas.copy()
        draw = ImageDraw.Draw(frame_img)
        
        wrapped = textwrap.wrap(chunk, width=18)
        y_text = int(target_h * 0.42)
        
        for line in wrapped:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            x = (target_w - w) / 2
            
            # Черная контурная обводка
            for adj in [(-4,0), (4,0), (0,-4), (0,4), (-4,-4), (4,4), (-4,4), (4,-4)]:
                draw.text((x + adj[0], y_text + adj[1]), line, font=font, fill="black")
            
            # Желтый текст
            draw.text((x, y_text), line, font=font, fill="yellow")
            y_text += 85

        path = f"chunk_{i}.jpg"
        frame_img.save(path)
        
        clip = ImageClip(path).set_duration(chunk_duration)
        clip = clip.resize(lambda t: 1 + 0.03 * t).set_position(('center', 'center'))
        clips.append(clip)

    final_clip = concatenate_videoclips(clips, method="compose")
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
    print("3. Генерируем нативную 9:16 картинку через Flux...")
    generate_ai_image(data['image_prompt'])
    print("4. Собираем вертикальное видео с бегущим текстом...")
    build_video(data['text'])
    print("5. Публикуем на YouTube...")
    upload_to_youtube(data)
