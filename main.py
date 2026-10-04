import os
import json
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai
from moviepy import ImageClip, AudioFileClip
import numpy as np

# Библиотеки для загрузки на YouTube через Google API
import google.auth
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

DATA_FILE = 'paradoxes.json'
OUTPUT_IMAGE = 'output.png'
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

def create_short_image(paradox):
    width, height = 1080, 1920
    image = Image.new("RGB", (width, height), color="#0F111A")
    draw = ImageDraw.Draw(image)
    
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
        font_body = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 45)
    except:
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()

    title = paradox["title"].upper()
    question = paradox["question"]
    answer = paradox["answer"]
    
    draw.text((80, 200), title, fill="#00FF66", font=font_title)
    
    def draw_wrapped_text(text, start_y, font, fill_color, max_width):
        lines = []
        words = text.split()
        current_line = ""
        for word in words:
            test_line = current_line + " " + word if current_line else word
            bbox = draw.textbbox((0, 0), test_line, font=font)
            w = bbox[2] - bbox[0]
            if w <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
            
        y = start_y
        for line in lines:
            draw.text((80, y), line, fill=fill_color, font=font)
            y += 70
        return y

    current_y = draw_wrapped_text(question, 400, font_body, "#FFFFFF", width - 160)
    draw.line([(80, current_y + 80), (width - 80, current_y + 80)], fill="#333842", width=4)
    
    draw_wrapped_text("ANSWER:", current_y + 150, font_title, "#FF3366", width - 160)
    draw_wrapped_text(answer, current_y + 250, font_body, "#A0A8B8", width - 160)

    image.save(OUTPUT_IMAGE)
    print(f"✅ Shorts card image created: {OUTPUT_IMAGE}")

def create_video_with_audio():
    duration = 12 
    image_clip = ImageClip(OUTPUT_IMAGE).with_duration(duration)
    
    if os.path.exists(BACKGROUND_AUDIO):
        audio_clip = AudioFileClip(BACKGROUND_AUDIO).subclip(0, duration)
        audio_clip = audio_clip.volumex(0.3)
        video_clip = image_clip.set_audio(audio_clip)
    else:
        print("⚠️ background.mp3 not found, generating video without audio.")
        video_clip = image_clip

    video_clip.write_videofile(
        OUTPUT_VIDEO,
        fps=24,
        codec='libx264',
        audio_codec='aac',
        preset='veryfast'
    )
    print(f"✅ Video generated: {OUTPUT_VIDEO}")

def upload_to_youtube(title):
    # Получаем токен из переменных окружения GitHub Secrets
    token_json = os.environ.get("YOUTUBE_TOKEN")
    client_secret_json = os.environ.get("CLIENT_SECRET_JSON")
    
    if not token_json:
        raise ValueError("❌ Не найден YOUTUBE_TOKEN в секретах!")

    # Восстанавливаем учетные данные для YouTube API
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

    # Параметры видео для Shorts
    body = {
        "snippet": {
            "title": f"{title} #shorts #paradox",
            "description": "Test your brain with this daily logic paradox! 🧠✨",
            "tags": ["paradox", "logic", "shorts", "brainteaser"],
            "categoryId": "27"  # Education
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
    print("🚀 Загрузка видео на YouTube...")
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Загрузка: {int(status.progress() * 100)}%")

    print(f"🎉 Успешно загружено! ID видео: {response.get('id')}")

if __name__ == "__main__":
    paradox = get_todays_paradox()
    print(f"Today's paradox: {paradox['title']}")
    
    create_short_image(paradox)
    create_video_with_audio()
    upload_to_youtube(paradox['title'])
