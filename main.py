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
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, CompositeAudioClip, AudioClip
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
    Write a short, hilarious IT meme script (2-3 short sentences) featuring funny animals (like cats or dogs) acting like human programmers.
    TOPIC: {selected_topic}.
    
    Voiceover guidelines:
    - Sarcastic, fast-paced developer moment.
    - END WITH: "Classic developer life!"
    
    Return ONLY a JSON object:
    {{
      "text": "Short spoken punchline here",
      "scenes": [
        "A funny Pixar 3D style cat programmer sweating heavily at a desk with multiple monitors, human-like posture, vertical 9:16",
        "A shocked Pixar 3D style cat looking at exploding code on a laptop screen, expressive face, vertical 9:16",
        "A chill Pixar 3D style cat drinking coffee surrounded by chaos, vertical 9:16"
      ],
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

def generate_scene_images(scenes):
    image_paths = []
    for i, prompt_text in enumerate(scenes):
        encoded_prompt = requests.utils.quote(prompt_text + ", Pixar 3D style, vibrant lighting, highly detailed, vertical 9:16")
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true&seed={random.randint(1, 100000)}"
        
        img_data = requests.get(url).content
        path = f"scene_{i}.jpg"
        with open(path, "wb") as f:
            f.write(img_data)
        image_paths.append(path)
    print("🎨 Набор Pixar-картинок с животными сгенерирован!")
    return image_paths

def generate_background_music(duration):
    # Генерация легкого ненавязчивого ритмичного фона (синусоидальные биты) чтобы видео не было «пустым» по звуку
    def make_frame(t):
        import math
        # Простой низкий электронный бит-фон
        freq = 110.0 if (int(t * 4) % 2 == 0) else 146.83
        val = math.sin(2 * math.pi * freq * t) * 0.05
        return [val, val]

    bg_music = AudioClip(make_frame, duration=duration, fps=22050)
    return bg_music

def build_video(script_text, scenes_prompts):
    audio = AudioFileClip("audio.mp3")
    total_duration = audio.duration
    target_w, target_h = 1080, 1920

    # Генерируем картинки под сцены
    image_paths = generate_scene_images(scenes_prompts)

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
        # Циклически выбираем картинку для текущего кусочка текста
        img_path = image_paths[i % len(image_paths)]
        img_base = Image.open(img_path).convert("RGB")
        
        img_w, img_h = img_base.size
        scale = max(target_w / img_w, target_h / img_h)
        new_w, new_h = int(img_w * scale), int(img_h * scale)
        img_base = img_base.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        frame_img = Image.new("RGB", (target_w, target_h), (0, 0, 0))
        frame_img.paste(img_base, ((target_w - new_w) // 2, (target_h - new_h) // 2))

        draw = ImageDraw.Draw(frame_img)
        wrapped = textwrap.wrap(chunk, width=18)
        
        # Текст ниже середины, но не у самого низа (на 55% высоте экрана)
        y_text = int(target_h * 0.55)
        
        for line in wrapped:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            x = (target_w - w) / 2
            
            # Жирная черная обводка
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

    final_visual = concatenate_videoclips(clips, method="compose")
    
    # Миксуем голос с фоновой музыкой
    bg_music = generate_background_music(total_duration)
    final_audio = CompositeAudioClip([audio, bg_music.volumethrough(0.2)])
    
    final_clip = final_visual.set_audio(final_audio)
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
    print("1. Генерируем IT-мем с животными...")
    data = get_script()
    print("2. Озвучиваем текст...")
    asyncio.run(create_audio(data['text']))
    print("3. Генерируем сцены с животными в стиле Pixar...")
    build_video(data['text'], data['scenes'])
    print("4. Публикуем на YouTube...")
    upload_to_youtube(data)
