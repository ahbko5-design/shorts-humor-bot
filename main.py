from PIL import Image
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

import os
import json
import time
import random
import asyncio
import textwrap
import numpy as np
from google import genai
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

# Расширенная база тем: кофейни, парки, лавочки, созвоны и жизненный абсурд
LIFE_TOPICS = [
    "trying to enjoy coffee in a park while thinking about work deadlines",
    "awkward moments during an online work meeting with camera accidentally on",
    "attempting to start a healthy lifestyle on Monday morning",
    "sitting on a park bench watching autumn leaves fall and questioning life choices",
    "waiting in line at a trendy coffee shop for a matcha latte",
    "working from a cozy coffee shop with bad Wi-Fi and overpriced pastry",
    "junior dev deleting production database on a Friday evening",
    "trying to look busy during a pointless corporate meeting",
    "staying up until 3 AM scrolling through reels instead of sleeping",
    "senior dev reviewing code and questioning humanity",
    "getting caught talking to yourself while debugging or thinking out loud",
    "the sheer panic when someone says 'we need to talk' at work"
]

def get_script_and_metadata():
    client = genai.Client(api_key=GEMINI_API_KEY)
    selected_topic = random.choice(LIFE_TOPICS)
    
    prompt = f"""
    Write a hilarious, relatable, short viral script for YouTube Shorts.
    THEME/SITUATION: {selected_topic}.
    Random seed: {random.randint(1000, 9999)}
    
    Guidelines:
    - Sarcastic, funny, highly relatable everyday moment or office humor.
    - Keep it punchy and engaging.
    - DO NOT include any calls to action or subscribe prompts. End with a strong punchline.
    
    Return ONLY a JSON object in this exact format:
    {{
      "text": "The full spoken text of the video without markdown or emojis",
      "title": "Life Be Like... 💀 #shorts #relatable #humor #lifestyle",
      "tags": ["Relatable", "Humor", "Life", "Shorts", "DayInTheLife"]
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

def get_local_bgm():
    # Ищем музыку в папке assets или в корне репозитория
    possible_paths = ["track1.mp3", "track2.mp3", "assets/track1.mp3", "assets/track2.mp3"]
    available_tracks = [p for p in possible_paths if os.path.exists(p)]
    
    if available_tracks:
        chosen = random.choice(available_tracks)
        print(f"🎵 Используем локальный трек: {chosen}")
        return chosen
    print("⚠️ Локальная музыка не найдена в репозитории, продолжаем без нее.")
    return None

def get_local_pixar_images():
    images_dir = "images"
    if not os.path.exists(images_dir):
        os.makedirs(images_dir, exist_ok=True)
        
    all_images = [os.path.join(images_dir, f) for f in os.listdir(images_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    
    if len(all_images) >= 3:
        chosen = random.sample(all_images, 3)
        print(f"🎨 Выбраны локальные картинки для смены кадров: {chosen}")
        return chosen
    elif len(all_images) > 0:
        chosen = [random.choice(all_images) for _ in range(3)]
        print(f"🎨 Картинок меньше трех, дублируем: {chosen}")
        return chosen
    else:
        print("⚠️ Папка images пуста! Создаем временные вертикальные заглушки.")
        fallback = []
        for i in range(3):
            path = f"scene_{i}.jpg"
            img = Image.new("RGB", (1080, 1920), (30, 30, 45))
            img.save(path)
            fallback.append(path)
        return fallback

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

        # Плавный Zoom-In эффект для оживления кадра
        img_clip = ImageClip(clean_path).set_duration(scene_duration)
        animated_clip = img_clip.resize(lambda t: 1 + 0.05 * (t / scene_duration)).set_position(('center', 'center'))
        scene_clips.append(animated_clip)

    from moviepy.editor import concatenate_videoclips
    bg_video = concatenate_videoclips(scene_clips)

    # Субтитры порциями по 4 слова
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

    # Смешиваем голос диктора и локальную фоновую музыку
    audio_tracks = [voice_audio]
    bgm_path = get_local_bgm()
    if bgm_path:
        try:
            bgm_clip = AudioFileClip(bgm_path).set_duration(total_duration)
            bgm_clip = volumex(bgm_clip, 0.15)  # Тихий фоновый звук на 15%
            audio_tracks.append(bgm_clip)
        except Exception as e:
            print(f"⚠️ Ошибка наложения фоновой музыки: {e}")

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
        f"✨ Relatable daily moments & life humor.\n\n"
        f"#shorts #relatable #humor #lifestyle #vibe"
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
    print(f"✅ ВИДЕО ОПУБЛИКОВАНО! ID: {response.get('id')}")

if __name__ == "__main__":
    print("1. Выбираем тему и генерируем скрипт через Gemini...")
    data = get_script_and_metadata()
    print("2. Озвучиваем текст...")
    asyncio.run(create_audio(data['text']))
    print("3. Подбираем локальные картинки из папки images...")
    image_files = get_local_pixar_images()
    print("4. Собираем видео с зумом, сменой 3 кадров, субтитрами и музыкой...")
    build_video(data['text'], image_files)
    print("5. Загружаем на YouTube...")
    upload_to_youtube(data)
