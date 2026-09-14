from PIL import Image
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

import os
import json
import time
import random
import requests
import asyncio
import textwrap
import numpy as np
from google import genai
from google.genai import types
import edge_tts
from PIL import ImageDraw, ImageFont
from moviepy.editor import ImageClip, AudioFileClip, VideoClip, CompositeVideoClip, CompositeAudioClip
from moviepy.audio.fx.all import volumex
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

FUNNY_BGM = [
    "https://cdn.pixabay.com/download/audio/2022/03/15/audio_c8c8a73467.mp3",
    "https://cdn.pixabay.com/download/audio/2022/01/18/audio_82c6d48227.mp3"
]

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

def get_script_and_image_prompts():
    client = genai.Client(api_key=GEMINI_API_KEY)
    selected_topic = random.choice(HUMOR_TOPICS)
    
    prompt = f"""
    Write a hilarious, relatable IT meme script.
    TOPIC: {selected_topic}.
    Random seed: {random.randint(1000, 9999)}
    
    Voiceover guidelines:
    - Sarcastic, fast-paced, relatable developer moment.
    - DO NOT include any calls to action or subscribe prompts. End with a strong punchline.
    
    We need 3 visual scenes for this joke featuring anthropomorphic animals in Disney Pixar 3D animation style (animals acting like human programmers/office workers).
    
    Return ONLY a JSON object in this exact format:
    {{
      "text": "The full spoken text of the video without markdown or emojis",
      "title": "IT Life Be Like... 💀 #shorts #ithumor #tech #programming",
      "tags": ["TechHumor", "ProgrammingMemes", "Coding", "DeveloperLife", "Shorts"],
      "image_prompts": [
        "A cute fluffy cat wearing glasses typing nervously on a tiny laptop in a messy office, Disney Pixar 3D animation style, highly detailed",
        "A stressed raccoon holding its head in paws staring at glowing error screens, office background, Disney Pixar 3D style",
        "A triumphant smug golden retriever dog leaning back in an office chair with coffee, Disney Pixar 3D style"
      ]
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
            print(f"⚠️ Попытка генерации скрипта {attempt + 1} не удалась ({e}). Ждем 15 сек...")
            time.sleep(15)
            
    raise Exception("❌ Ошибка при генерации скрипта через Gemini.")

async def create_audio(text):
    voice = "en-US-EricNeural" 
    communicate = edge_tts.Communicate(text, voice, rate="+15%", pitch="+5Hz")
    await communicate.save("audio.mp3")

def download_bgm():
    bgm_url = random.choice(FUNNY_BGM)
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        }
        res = requests.get(bgm_url, headers=headers, timeout=15)
        if res.status_code == 200 and 'audio' in res.headers.get('Content-Type', '').lower():
            with open("bgm.mp3", "wb") as f:
                f.write(res.content)
            print("🎵 Фоновая музыка успешно скачана!")
        else:
            print("⚠️ Музыка не скачана (защита сайта), продолжаем без нее.")
            if os.path.exists("bgm.mp3"):
                os.remove("bgm.mp3")
    except Exception as e:
        print(f"⚠️ Ошибка при скачивании музыки: {e}")

def generate_pixar_images(prompts):
    client = genai.Client(api_key=GEMINI_API_KEY)
    image_paths = []
    
    for i, p_text in enumerate(prompts[:3]):
        print(f"🎨 Генерируем 3D Pixar картинку {i+1}/3 через Imagen 3...")
        try:
            result = client.models.generate_images(
                model='imagen-3.0-generate-002',
                prompt=p_text + ", vertical 9:16 aspect ratio, cinematic lighting, 4k",
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    output_mime_type="image/jpeg",
                    aspect_ratio="9:16",
                )
            )
            for gen_img in result.generated_images:
                path = f"scene_{i}.jpg"
                with open(path, "wb") as f:
                    f.write(gen_img.image.image_bytes)
                image_paths.append(path)
                print(f"✅ Картинка {i+1} успешно создана и сохранена!")
        except Exception as e:
            print(f"❌ ОШИБКА генерации Imagen для картинки {i+1}: {e}")

    if not image_paths:
        raise Exception("❌ Не удалось сгенерировать ни одной картинки через Imagen API.")
            
    return image_paths

def build_video(script_text, image_paths):
    voice_audio = AudioFileClip("audio.mp3")
    total_duration = voice_audio.duration
    target_w, target_h = 1080, 1920

    num_scenes = len(image_paths)
    scene_duration = total_duration / num_scenes

    scene_clips = []
    for i, img_path in enumerate(image_paths):
        img = Image.open(img_path).convert("RGB")
        orig_w, orig_h = img.size
        scale = max(target_w / orig_w, target_h / orig_h)
        new_w, new_h = int(orig_w * scale), int(orig_h * scale)
        img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        cropped_img = img_resized.crop((left, top, left + target_w, top + target_h))
        clean_path = f"clean_scene_{i}.jpg"
        cropped_img.save(clean_path)

        img_clip = ImageClip(clean_path).set_duration(scene_duration)
        animated_clip = img_clip.resize(lambda t: 1 + 0.05 * (t / scene_duration)).set_position(('center', 'center'))
        scene_clips.append(animated_clip)

    from moviepy.editor import concatenate_videoclips
    bg_video = concatenate_videoclips(scene_clips)

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
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 56)
    except:
        font = ImageFont.load_default()

    def make_caption_frame(t):
        chunk_idx = min(int(t / chunk_duration), len(chunks) - 1)
        current_text = chunks[chunk_idx]

        txt_image = Image.new("RGB", (target_w, target_h), (0, 0, 0))
        draw = ImageDraw.Draw(txt_image)

        wrapped = textwrap.wrap(current_text, width=18)
        y_text = int(target_h * 0.36)

        for line in wrapped:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            x = (target_w - w) / 2

            for adj in [(-4,0), (4,0), (0,-4), (0,4), (-4,-4), (4,4), (-4,4), (4,-4)]:
                draw.text((x + adj[0], y_text + adj[1]), line, font=font, fill="black")

            draw.text((x, y_text), line, font=font, fill="yellow")
            y_text += 75

        return np.array(txt_image)

    def make_mask_frame(t):
        chunk_idx = min(int(t / chunk_duration), len(chunks) - 1)
        current_text = chunks[chunk_idx]

        mask_image = Image.new("L", (target_w, target_h), 0)
        draw = ImageDraw.Draw(mask_image)

        wrapped = textwrap.wrap(current_text, width=18)
        y_text = int(target_h * 0.36)

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

    final_clip = CompositeVideoClip([bg_video, caption_clip], size=(target_w, target_h))

    audio_tracks = [voice_audio]
    if os.path.exists("bgm.mp3"):
        try:
            bgm_clip = AudioFileClip("bgm.mp3").set_duration(total_duration)
            bgm_clip = volumex(bgm_clip, 0.15)
            audio_tracks.append(bgm_clip)
        except Exception as e:
            print(f"⚠️ Ошибка наложения музыки: {e}")

    final_audio = CompositeAudioClip(audio_tracks)
    final_clip = final_clip.set_audio(final_audio)

    final_clip.write_videofile("final_short.mp4", fps=24, codec="libx264", audio_codec="aac")
    voice_audio.close()

def upload_to_youtube(metadata):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    
    with open('token.json', 'r') as f:
        token_data = json.load(f)

    creds = Credentials(
        token=token_data.get('token'),
        refresh_token=token_data.get('refresh_token'),
        token_uri=token_data.get('token_uri', "https://oauth2.googleapis.com/token"),
        client_id=token_data.get('client_id'),
        client_secret=token_data.get('client_secret'),
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )

    if creds.expired and creds.refresh_token:
        print("🔄 Обновляем истёкший access token...")
        creds.refresh(Request())
        
    youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)

    description_text = (
        f"{metadata['text']}\n\n"
        f"🐾 Pixar-style animal IT humor & dev life moments.\n\n"
        f"#shorts #ithumor #programming #coding #pixar"
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
    print(f"✅ ПИКСАР-МЕМ ОПУБЛИКОВАН! ID: {response.get('id')}")

if __name__ == "__main__":
    print("1. Генерируем IT-мем и промпты для Pixar-картинок...")
    data = get_script_and_image_prompts()
    print("2. Озвучиваем текст...")
    asyncio.run(create_audio(data['text']))
    print("3. Скачиваем фоновую музыку...")
    download_bgm()
    print("4. Генерируем 3 вертикальные 9:16 картинки через Imagen 3...")
    image_files = generate_pixar_images(data['image_prompts'])
    print("5. Собираем видео с зумом, сменой кадров и субтитрами...")
    build_video(data['text'], image_files)
    print("6. Загружаем на YouTube...")
    upload_to_youtube(data)
