import os
import json
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai
from moviepy import ImageClip, AudioFileClip, concatenate_videoclips
import numpy as np

import google.auth
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

DATA_FILE = 'paradoxes.json'
OUTPUT_VIDEO = 'output.mp4'
BACKGROUND_AUDIO = 'background.mp3'

def load_database():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_database(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_todays_paradox():
    data = load_database()
    if not data:
        data = [{"id": 1, "title": "Paradox", "question": "What came first?", "answer": "Nobody knows."}]
    
    day_of_year = datetime.now().timetuple().tm_yday
    index = (day_of_year - 1) % len(data)
    paradox = data[index]
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key and len(data) < 365:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            prompt = "Create a new, unique, short philosophical or scientific paradox in English. Return the result STRICTLY as a JSON object without any markdown wrapping: {\"title\": \"Title\", \"question\": \"The mystery question\", \"answer\": \"Short answer\"}"
            response = model.generate_content(prompt)
            new_item = json.loads(response.text.strip())
            new_item["id"] = len(data) + 1
            data.append(new_item)
            save_database(data)
            print(f"✨ New paradox generated and added: {new_item['title']}")
        except Exception as e:
            print(f"Failed to auto-generate new paradox via API: {e}")
            
    return paradox

def draw_slide(title, question, answer=None, filename="slide.png"):
    width, height = 1080, 1920
    # Глубокий премиальный темный фон
    image = Image.new("RGB", (width, height), color="#0B0D13")
    draw = ImageDraw.Draw(image)
    
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
        font_body = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 44)
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

    # 1. Плашка-шапка для заголовка (делает дизайн дорогим и структурированным)
    title_lines = wrap_text(title.upper(), font_title, max_text_width - 60)
    
    # Рисуем красивую неоновую рамку сверху для заголовка
    header_box_height = len(title_lines) * 65 + 60
    draw.rounded_rectangle([80, 140, width - 80, 140 + header_box_height], radius=20, fill="#151922", outline="#00FF66", width=2)
    
    y = 140 + 30
    for line in title_lines:
        bbox = draw.textbbox((0, 0), line, font=font_title)
        w = bbox[2] - bbox[0]
        draw.text(((width - w) / 2, y), line, fill="#00FF66", font=font_title)
        y += 65

    # 2. Блок с вопросом (в центре экрана, безопасная зона от правых кнопок YouTube)
    q_lines = wrap_text(question, font_body, max_text_width - 60)
    q_box_height = len(q_lines) * 60 + 80
    q_box_top = 140 + header_box_height + 40
    
    draw.rounded_rectangle([80, q_box_top, width - 80, q_box_top + q_box_height], radius=20, fill="#131720", outline="#2A3245", width=2)
    
    y = q_box_top + 40
    for line in q_lines:
        draw.text((110, y), line, fill="#FFFFFF", font=font_body)
        y += 60

    # 3. Если передан ответ — рисуем блок ответа ниже
    if answer:
        ans_lines = wrap_text(answer, font_body, max_text_width - 60)
        ans_box_height = len(ans_lines) * 60 + 100
        ans_box_top = q_box_top + q_box_height + 40
        
        draw.rounded_rectangle([80, ans_box_top, width - 80, ans_box_top + ans_box_height], radius=20, fill="#1A131C", outline="#FF3366", width=2)
        
        # Метка ANSWER
        draw.text((110, ans_box_top + 25), "💡 ANSWER:", fill="#FF3366", font=font_title)
        
        y = ans_box_top + 95
        for line in ans_lines:
            draw.text((110, y), line, fill="#E2E8F0", font=font_body)
            y += 60

    # Футер / Бренд канала внизу
    draw.text((width / 2 - 120, height - 100), "🧩 Paradox Lab", fill="#64748B", font=font_body)

    image.save(filename)

def create_dynamic_video(paradox):
    duration = 14
    split_time = 9.0  # 9 секунд зритель думает над загадкой, последние 5 секунд видит ответ

    # Генерируем два красивых кадра
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
    print(f"✅ Стильное видео с таймингом создано: {OUTPUT_VIDEO}")

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

    media = MediaFileUpload(OUTPUT_VIDEO, chunksize=-1, resumable=True)
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = None
    print("🚀 Загрузка стильного шортса...")
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Загрузка: {int(status.progress() * 100)}%")

    print(f"🎉 Успешно опубликовано! ID видео: {response.get('id')}")

if __name__ == "__main__":
    paradox = get_todays_paradox()
    print(f"Today's paradox: {paradox['title']}")
    
    create_dynamic_video(paradox)
    upload_to_youtube(paradox['title'])
