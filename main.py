import os
import json
import time
import random
import urllib.request
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai
from moviepy import ImageClip, AudioFileClip, concatenate_videoclips
import numpy as np

import google.auth
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

HISTORY_FILE = 'history.txt'
OUTPUT_VIDEO = 'output.mp4'
BACKGROUND_AUDIO = 'background.mp3'

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f.readlines() if line.strip()]

def save_to_history(title):
    with open(HISTORY_FILE, 'a', encoding='utf-8') as f:
        f.write(title + "\n")

def generate_unique_paradox():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("❌ Не найден GEMINI_API_KEY в секретах!")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    history = load_history()
    avoid_list = ", ".join(history[-20:]) if history else "none"

    prompt = f"""
    Create a new, unique, short philosophical or scientific paradox in English. 
    It must NOT be any of these recently used topics: [{avoid_list}].
    Return the result STRICTLY as a JSON object without any markdown wrapping, using this exact format: 
    {{"title": "Title", "question": "The mystery question", "answer": "Short answer"}}
    """

    for attempt in range(3):
        try:
            response = model.generate_content(prompt)
            text = response.text.strip()
            # Очищаем от возможных маркдаун-оберток если модель их добавила
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            text = text.strip()
            
            paradox = json.loads(text)
            title = paradox.get("title")
            
            if title and title not in history:
                save_to_history(title)
                print(f"✨ Сгенерирован новый уникальный парадокс: {title}")
                return paradox
        except Exception as e:
            print(f"⚠️ Попытка генерации {attempt + 1} не удалась: {e}")
            
    # Запасной вариант, если API затупит
    return {
        "title": f"The Quantum Observer Paradox #{random.randint(100, 999)}",
        "question": "Does the universe exist when nobody is looking at it?",
        "answer": "Quantum mechanics suggests observation collapses wavefunctions into reality."
    }

def ensure_background_audio():
    if not os.path.exists(BACKGROUND_AUDIO):
        print("📥 Скачивание фоновой музыки...")
        try:
            audio_url = "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf756.mp3?filename=cyberpunk-luci-103357.mp3"
            urllib.request.urlretrieve(audio_url, BACKGROUND_AUDIO)
            print("✅ Фоновая музыка успешно загружена!")
        except Exception as e:
            print(f"⚠️ Не удалось скачать музыку: {e}")

def draw_slide(title, question, answer=None, filename="slide.png"):
    width, height = 1080, 1920
    
    image = Image.new("RGB", (width, height), color="#07090E")
    draw = ImageDraw.Draw(image)
    
    for _ in range(6):
        rx = random.randint(0, width)
        ry = random.randint(0, height)
        r = random.randint(300, 700)
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        d_layer = ImageDraw.Draw(layer)
        d_layer.ellipse([rx - r, ry - r, rx + r, ry + r], fill=(0, 255, 102, 8))
        image = Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")
    
    draw = ImageDraw.Draw(image)
    
    grid_step = 120
    for x in range(0, width, grid_step):
        draw.line([(x, 0), (x, height)], fill="#111622", width=1)
    for y in range(0, height, grid_step):
        draw.line([(0, y), (width, y)], fill="#111622", width=1)

    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 50)
        font_body = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 42)
    except:
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()

    def wrap_text(text, font, max_width):
        lines = []
        for paragraph in text.split('\n'):
            words = paragraph.split()
            current_line = ""
            for word in words:
                test_line = current_line + " " + word if current_line else word
                bbox = draw.textbbox((0, 0), test_line, font=font)
                if (bbox[2] - bbox[0]) <= max_width:
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)
        return lines

    max_text_width = width - 160
    start_y = 280
    
    title_lines = wrap_text(title.upper(), font_title, max_text_width - 60)
    header_box_height = len(title_lines) * 60 + 50
    
    draw.rounded_rectangle([80, start_y, width - 80, start_y + header_box_height], radius=20, fill="#0F131D", outline="#00FF66", width=2)
    
    y = start_y + 25
    for line in title_lines:
        bbox = draw.textbbox((0, 0), line, font=font_title)
        w = bbox[2] - bbox[0]
        draw.text(((width - w) / 2, y), line, fill="#00FF66", font=font_title)
        y += 60

    q_lines = wrap_text(question, font_body, max_text_width - 60)
    q_box_height = len(q_lines) * 55 + 60
    q_box_top = start_y + header_box_height + 40
    
    draw.rounded_rectangle([80, q_box_top, width - 80, q_box_top + q_box_height], radius=20, fill="#0D111A", outline="#222B3E", width=2)
    
    y = q_box_top + 30
    for line in q_lines:
        draw.text((110, y), line, fill="#FFFFFF", font=font_body)
        y += 55

    if answer:
        ans_lines = wrap_text(answer, font_body, max_text_width - 60)
        ans_box_height = len(ans_lines) * 55 + 90
        ans_box_top = q_box_top + q_box_height + 30
        
        draw.rounded_rectangle([80, ans_box_top, width - 80, ans_box_top + ans_box_height], radius=20, fill="#160E14", outline="#FF3366", width=2)
        
        draw.text((110, ans_box_top + 20), "💡 ANSWER:", fill="#FF3366", font=font_title)
        
        y = ans_box_top + 80
        for line in ans_lines:
            draw.text((110, y), line, fill="#E2E8F0", font=font_body)
            y += 55
        
        draw.text((width / 2 - 140, height - 160), "✨ SOLUTION UNLOCKED", fill="#FF3366", font=font_body)
    else:
        draw.rounded_rectangle([80, height - 200, width - 80, height - 140], radius=15, fill="#0F131D", outline="#00FF66", width=1)
        draw.text((width / 2 - 180, height - 185), "⏳ THINK... ANSWER SOON", fill="#00FF66", font=font_body)

    image.save(filename)

def create_dynamic_video(paradox):
    duration = 14
    split_time = 9.0

    draw_slide(paradox["title"], paradox["question"], answer=None, filename="slide1.png")
    draw_slide(paradox["title"], paradox["question"], answer=paradox["answer"], filename="slide2.png")

    clip1 = ImageClip("slide1.png").with_duration(split_time)
    clip2 = ImageClip("slide2.png").with_duration(duration - split_time)
    
    video_clip = concatenate_videoclips([clip1, clip2])

    if os.path.exists(BACKGROUND_AUDIO):
        audio_clip = AudioFileClip(BACKGROUND_AUDIO).subclip(0, duration).volumex(0.6)
        video_clip = video_clip.with_audio(audio_clip)

    video_clip.write_videofile(
        OUTPUT_VIDEO,
        fps=24,
        codec='libx264',
        audio_codec='aac',
        preset='veryfast'
    )
    print(f"✅ Video created successfully: {OUTPUT_VIDEO}")

def upload_to_youtube(title):
    token_json = os.environ.get("YOUTUBE_TOKEN")
    client_secret_json = os.environ.get("CLIENT_SECRET_JSON")
    
    if not token_json:
        raise ValueError("❌ Не найден YOUTUBE_TOKEN!")

    token_data = json.loads(token_json)
    client_data = json.loads(client_secret_json) if client_secret_json else {}
    
    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data.get("client_id", client_data.get("client_id")),
        client_secret=token_data.get("client_secret", client_data.get("client_secret")),
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )

    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": f"{title} #shorts #paradox #brainteaser",
            "description": "Can you solve this logic puzzle? Think before the answer drops! 🧠⚡️",
            "tags": ["paradox", "logic", "shorts", "brainteaser", "puzzle"],
            "categoryId": "27"
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            media = MediaFileUpload(OUTPUT_VIDEO, chunksize=-1, resumable=True)
            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            )

            response = None
            print(f"🚀 Загрузка на YouTube (попытка {attempt + 1})...")
            while response is None:
                status, response = request.next_chunk()
                if status:
                    print(f"Загрузка: {int(status.progress() * 100)}%")

            print(f"🎉 Успешно опубликовано! ID видео: {response.get('id')}")
            return
        except HttpError as e:
            print(f"⚠️ Ошибка YouTube API при попытке {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                print("⏳ Ждем 5 секунд и повторяем...")
                time.sleep(5)
            else:
                raise e

if __name__ == "__main__":
    paradox = generate_unique_paradox()
    print(f"Today's paradox: {paradox['title']}")
    
    ensure_background_audio()
    create_dynamic_video(paradox)
    upload_to_youtube(paradox['title'])
