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

FALLBACK_SCRIPTS = [
    {
        "text": "Fixed one bug in production, created ten brand new features for the QA team. You are welcome! Subscribe to Tech Humor Lab for daily IT laughs!",
        "image_prompt": "3D Pixar animation style, stressed funny 3D programmer character facepalm at glowing laptop screen, red error lights",
        "title": "One Bug Fixed, Ten Born... 💀 #shorts #ithumor #tech #programming",
        "tags": ["TechHumor", "ProgrammingMemes", "Coding", "DeveloperLife", "Shorts"]
    },
    {
        "text": "Deploying code on Friday at five PM without testing. What could possibly go wrong? Subscribe to Tech Humor Lab for daily IT laughs!",
        "image_prompt": "3D Pixar animation style, cute 3D cat programmer wearing hoodie panicking near burning server room",
        "title": "Friday Deployment Be Like... 💀 #shorts #ithumor #tech #programming",
        "tags": ["TechHumor", "ProgrammingMemes", "Coding", "DeveloperLife", "Shorts"]
    }
]

def get_script():
    client = genai.Client(api_key=GEMINI_API_KEY)
    selected_topic = random.choice(HUMOR_TOPICS)
    
    prompt = f"""
    Write a short, hilarious, punchy IT meme script (2-3 sentences max).
    TOPIC: {selected_topic}.
    
    Voiceover guidelines:
    - Sarcastic, fast-paced developer moment.
    - END WITH: "Subscribe to Tech Humor Lab for daily IT laughs!"
    
    Return ONLY a JSON object:
    {{
      "text": "The full spoken text of the video without markdown or emojis",
      "image_prompt": "3D Pixar animation style, cute expressive 3D character programmer or cat reacting to a glowing laptop screen with red error code, cinematic lighting, 3d render",
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
            json_str = raw[start:end]
            return json.loads(json_str)
        except Exception as e:
            err_msg = str(e)
            match = re.search(r"retryDelay': '(\d+)s'", err_msg)
            wait_time = int(match.group(1)) + 2 if match else 40
            print(f"⚠️ Лимит Gemini (429). Попытка {attempt + 1}/5. Ждём {wait_time} сек...")
            time.sleep(wait_time)
            
    print("⚠️ Лимиты API исчерпаны. Запускаем резервный готовый мем...")
    return random.choice(FALLBACK_SCRIPTS)

async def create_audio(text):
    voice = "en-US-EricNeural" 
    communicate = edge_tts.Communicate(text, voice, rate="+15%", pitch="+5Hz")
    await communicate.save("audio.mp3")

def generate_ai_image(image_prompt):
    encoded_prompt = requests.utils.quote(f"{image_prompt}, 3d pixar style, highly detailed, 8k resolution")
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true&seed={random.randint(1, 100000)}"
    
    res = requests.get(url)
    with open("meme_bg.jpg", "wb") as f:
        f.write(res.content)
    print("🎨 ИИ-изображение успешно скачано!")

def build_video(script_text):
    audio = AudioFileClip("audio.mp3")
    total_duration = audio.duration
    target_w, target_h = 1080, 1920

    img = Image.open("meme_bg.jpg").convert("RGB")
    orig_w, orig_h = img.size

    scale = max(target_w / orig_w, target_h / orig_h)
    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)

    img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    bg_canvas = img_resized.crop((left, top, left + target_w, top + target_h))

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

    clips = []
    for i, chunk in enumerate(chunks):
        frame_img = bg_canvas.copy()
        draw = ImageDraw.Draw(frame_img)

        wrapped = textwrap.wrap(chunk, width=18)
        y_text = int(target_h * 0.38)

        for line in wrapped:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            x = (target_w - w) / 2

            for adj in [(-4,0), (4,0), (0,-4), (0,4), (-4,-4), (4,4), (-4,4), (4,-4)]:
                draw.text((x + adj[0], y_text + adj[1]), line, font=font, fill="black")

            draw.text((x, y_text), line, font=font, fill="yellow")
            y_text += 75

        frame_path = f"chunk_{i}.jpg"
        frame_img.save(frame_path)
        
        c = ImageClip(frame_path).set_duration(chunk_duration)
        clips.append(c)

    final_visual = concatenate_videoclips(clips, method="compose")
    final_animated = final_visual.resize(lambda t: 1 + 0.04 * (t / total_duration))
    
    final_clip = final_animated.set_audio(audio)
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
    print("1. Генерируем короткий IT-мем...")
    data = get_script()
    print("2. Озвучиваем текст...")
    asyncio.run(create_audio(data['text']))
    print("3. Генерируем Pixar 3D визуал...")
    generate_ai_image(data['image_prompt'])
    print("4. Собираем 9:16 видео с бегущим текстом...")
    build_video(data['text'])
    print("5. Публикуем на YouTube...")
    upload_to_youtube(data)
