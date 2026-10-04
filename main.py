import os
import json
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai

# Настройка путей и файлов
DATA_FILE = 'paradoxes.json'
OUTPUT_IMAGE = 'output.png'

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
        data = [{"id": 1, "title": "Парадокс", "question": "Что было раньше?", "answer": "Никто не знает."}]
    
    # Выбираем парадокс по дню года, чтобы он циклично шел по кругу
    day_of_year = datetime.now().timetuple().tm_yday
    index = (day_of_year - 1) % len(data)
    
    paradox = data[index]
    
    # Опционально: если забит GEMINI_API_KEY, можно периодически генерировать свежие
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key and len(data) < 365:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            prompt = "Придумай новый уникальный короткий философский или научный парадокс (на русском языке). Верни результат СТРОГО в формате JSON без markdown-обертки: {\"title\": \"Название\", \"question\": \"Суть загадки\", \"answer\": \"Короткий ответ\"}"
            response = model.generate_content(prompt)
            new_item = json.loads(response.text.strip())
            new_item["id"] = len(data) + 1
            data.append(new_item)
            save_database(data)
            print(f"✨ Сгенерирован и добавлен новый парадокс: {new_item['title']}")
        except Exception as e:
            print(f"Не удалось автосгенерировать новый парадокс через API: {e}")
            
    return paradox

def create_short_image(paradox):
    width, height = 1080, 1920
    # Глубокий темный фон в стиле киберпанк/техно
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
    
    # Рисуем заголовок ярко-зеленым неона
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

    # Рисуем вопрос
    current_y = draw_wrapped_text(question, 400, font_body, "#FFFFFF", width - 160)
    
    # Разделитель
    draw.line([(80, current_y + 80), (width - 80, current_y + 80)], fill="#333842", width=4)
    
    # Рисуем ответ
    draw_wrapped_text("ОТВЕТ:", current_y + 150, font_title, "#FF3366", width - 160)
    draw_wrapped_text(answer, current_y + 250, font_body, "#A0A8B8", width - 160)

    image.save(OUTPUT_IMAGE)
    print(f"✅ Карточка для Shorts успешно создана: {OUTPUT_IMAGE}")

if __name__ == "__main__":
    paradox = get_todays_paradox()
    print(f"Выбран парадокс на сегодня: {paradox['title']}")
    create_short_image(paradox)
