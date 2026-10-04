import os
import json
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai
from moviepy import ImageClip, AudioFileClip, CompositeVideoClip
import numpy as np

DATA_FILE = 'paradoxes.json'
OUTPUT_IMAGE = 'output.png'
OUTPUT_VIDEO = 'output.mp4'
# Путь к фоновой музыке (можно положить в репозиторий MP3-файл, например 'background.mp3')
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
    
    # Автогенерация нового парадокса, если база меньше 365 штук
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
    # Длительность ролика под Shorts — 12 секунд (оптимально для чтения текста)
    duration = 12 
    
    # Создаем клип из картинки
    image_clip = ImageClip(OUTPUT_IMAGE).set_duration(duration)
    
    # Если в репозитории есть файл фоновой музыки, подмешиваем его
    if os.path.exists(BACKGROUND_AUDIO):
        audio_clip = AudioFileClip(BACKGROUND_AUDIO).subclip(0, duration)
        # Немного приглушаем громкость музыки, чтобы она была фоновой
        audio_clip = audio_clip.volumex(0.3)
        video_clip = image_clip.set_audio(audio_clip)
    else:
        print("⚠️ Файл background.mp3 не найден, видео будет без звука. Добавь MP3 в репозиторий, если нужна музыка!")
        video_clip = image_clip

    # Экспортируем готовый файл видео
    video_clip.write_videofile(
        OUTPUT_VIDEO,
        fps=24,
        codec='libx264',
        audio_codec='aac',
        preset='veryfast'
    )
    print(f"✅ Shorts video with music successfully generated: {OUTPUT_VIDEO}")

if __name__ == "__main__":
    paradox = get_todays_paradox()
    print(f"Today's paradox: {paradox['title']}")
    create_short_image(paradox)
    create_video_with_audio()
