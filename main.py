import os
import json
import time
import random
import asyncio
import textwrap
import requests
from google import genai
import edge_tts
from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip
import google_auth_oauthlib.flow
import googleapiclient.discovery
from googleapiclient.http import MediaFileUpload

# 1. Восстановление секретов и файлов авторизации
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
    Write a hilarious, relatable IT meme script.
    TOPIC: {selected_topic}.
    Random seed: {random.randint(1000, 9999)}
    
    Voiceover guidelines:
    - Sarcastic, fast-paced developer moment.
    - END WITH: "Subscribe to Tech Humor Lab for daily IT laughs!"
    
    Return ONLY a JSON object:
    {{
      "text": "The full spoken text of the video without markdown or emojis",
      "image_prompt": "A funny detailed meme visual, highly detailed 3D render style, vertical 9:16 composition. Example: A fluffy cat wearing a yellow hoodie looking shocked at a laptop screen with red error code",
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
            raw_text = response.text.strip()
            raw_text = raw_text.replace("```json", "").replace("```", "").strip()
            return json.loads(raw_text)
        except Exception as e:
            print(f"⚠️ Попытка {attempt + 1} не удалась ({e}). Ждем 15 сек...")
            time.sleep(15)
            
    raise Exception("❌ Ошибка при генерации через Gemini.")

async def create_audio(text):
    voice = "en-US-EricNeural" 
    communicate = edge_tts.Communicate(text, voice, rate="+15%", pitch="+5Hz")
    await communicate.save("audio.mp3")

def generate_ai_image(image_prompt):
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    try:
        # Попытка 1: Imagen 3
        result = client.models.generate_images(
            model='imagen-3.0-generate-002',
            prompt=image_prompt + ", 9:16 vertical aspect ratio, full screen",
            config=dict(
                number_of_images=1,
                output_mime_type="image/jpeg",
                aspect_ratio="9:16"
            )
        )
        for generated_image in result.generated_images:
            with open("meme_bg.jpg", "wb") as f:
                f.write(generated_image.image.image_bytes)
            print("🎨 Изображение сгенерировано через Imagen 3!")
            return
    except Exception as e:
        print(f"⚠️ Ошибка Imagen 3: {e}. Переходим на резервный генератор...")
        
        # Резервный источник ИИ-картинок (Pollinations AI)
        encoded_prompt = requests.utils.quote(image_prompt + " vertical 9:16 meme high quality")
        fallback_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true"
        img_data = requests.get(fallback_url).content
        with open("meme_bg.jpg", "wb") as f:
            f.write(img_data)
        print("🎨 Изображение сгенерировано через резервный API!")

def build_video(script_text):
    audio = AudioFileClip("audio.mp3")
    duration = audio.duration

    img_clip = ImageClip("meme_bg.jpg").set_duration(duration)
    img_w, img_h = img_clip.size
    target_w, target_h = 1080, 1920
    
    scale = max(target_w / img_w, target_h / img_h)
    new_w, new_h = int(img_w * scale), int(img_h * scale)
    
    img_resized = img_clip.resize((new_w, new_h))
    img_cropped = img_resized.crop(x_center=new_w/2, y_center=new_h/2, width=target_w, height=target_h)

    img_animated = img_cropped.resize(lambda t: 1 + 0.04 * t).set_position(('center', 'center'))
    wrapped_text = "\n".join(textwrap.wrap(script_text, width=25))

    try:
        txt_clip = (TextClip(
                        txt=wrapped_text, 
                        fontsize=48, 
                        color='yellow', 
                        font='DejaVu-Sans-Bold',
                        stroke_color='black',
                        stroke_width=4,
                        method='caption',
                        align='center',
                        size=(900, None)
                    )
                    .set_position(('center', 0.30), relative=True) 
                    .set_duration(duration))

        final_clip = CompositeVideoClip([img_animated, txt_clip], size=(target_w, target_h))
    except Exception as e:
        print(f"⚠️ Ошибка субтитров: {e}. Монтируем без текста.")
        final_clip = CompositeVideoClip([img_animated], size=(target_w, target_h))

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
    print("3. Генерируем ИИ-мем в формате 9:16...")
    generate_ai_image(data['image_prompt'])
    print("4. Собираем ролик...")
    build_video(data['text'])
    print("5. Публикуем на YouTube...")
    upload_to_youtube(data)
