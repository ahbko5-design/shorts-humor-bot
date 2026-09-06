import os
import json
import time
import requests
import asyncio
from google import genai
import edge_tts
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip
import google_auth_oauthlib.flow
import googleapiclient.discovery
from googleapiclient.http import MediaFileUpload

# 1. Восстановление конфигов из секретов GitHub
if not os.path.exists('client_secret.json'):
    with open('client_secret.json', 'w') as f:
        f.write(os.getenv('CLIENT_SECRET_JSON'))

if not os.path.exists('token.json'):
    with open('token.json', 'w') as f:
        f.write(os.getenv('YOUTUBE_TOKEN'))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

# --- СЦЕНАРИЙ (IT-ЮМОР) ---
def get_script():
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = """
    Write a 20-second funny, sarcastic, and relatable joke or story about working in tech, programming, or corporate office life.
    Topics: bugs in production, unexpected client requests, endless Zoom calls, junior vs senior devs.
    
    Voiceover guidelines:
    - Fast-paced, witty, sarcastic.
    - END WITH: "Subscribe to Tech Humor Lab for daily developer laughs!"
    
    Return ONLY a JSON object with this exact structure:
    {
      "text": "The full spoken text of the video without markdown or emojis",
      "query": "single search keyword for stock video like computer or office or frustration or typing",
      "title": "When you test in production 💀 #shorts #ithumor #tech",
      "tags": ["TechHumor", "Programming", "CodingMemes", "OfficeLife", "Shorts"]
    }
    """
    
    for attempt in range(5):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            clean_json = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_json)
        except Exception as e:
            print(f"⚠️ Попытка {attempt + 1} не удалась ({e}). Ждем 15 секунд...")
            time.sleep(15)
            
    raise Exception("❌ Не удалось получить ответ от Gemini после 5 попыток.")

# --- ОЗВУЧКА (ДИНАМИЧНЫЙ ГОЛОС) ---
async def create_audio(text):
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save("audio.mp3")

# --- ФОНОВОЕ ВИДЕО ---
def download_pexels_video(query):
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={query}&per_page=1&orientation=portrait"
    res = requests.get(url, headers=headers).json()
    
    if not res.get("videos"):
        res = requests.get("https://api.pexels.com/videos/search?query=computer&per_page=1&orientation=portrait", headers=headers).json()

    video_url = res["videos"][0]["video_files"][0]["link"]
    with open("background.mp4", "wb") as f:
        f.write(requests.get(video_url).content)

# --- МОНТАЖ С НАЛОЖЕНИЕМ ТЕКСТА ---
def build_video(script_text):
    audio = AudioFileClip("audio.mp3")
    video = VideoFileClip("background.mp4")

    if video.duration < audio.duration:
        video = video.loop(duration=audio.duration)
    else:
        video = video.subclip(0, audio.duration)

    video = video.set_audio(audio)

    try:
        txt_clip = (TextClip(
                        txt=script_text, 
                        fontsize=42, 
                        color='yellow', 
                        font='Arial-Bold',
                        stroke_color='black',
                        stroke_width=2,
                        method='caption',
                        size=(int(video.w * 0.85), None)
                    )
                    .set_position('center')
                    .set_duration(audio.duration))

        final_clip = CompositeVideoClip([video, txt_clip])
    except Exception as e:
        print(f"⚠️ Ошибка создания субтитров ({e}), собираем видео без них.")
        final_clip = video

    final_clip.write_videofile("final_short.mp4", fps=24, codec="libx264", audio_codec="aac")
    audio.close()
    video.close()

# --- ПУБЛИКАЦИЯ ---
def upload_to_youtube(metadata):
    from google.oauth2.credentials import Credentials
    
    creds = Credentials.from_authorized_user_file('token.json', ["https://www.googleapis.com/auth/youtube.upload"])
    youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)

    description_text = (
        f"{metadata['text']}\n\n"
        f"💀 Relatable IT humor, developer life, and office reality.\n"
        f"🔔 Subscribe to Tech Humor Lab for daily laughs!\n\n"
        f"#shorts #ithumor #programming #coding #tech"
    )

    body = {
        'snippet': {
            'title': metadata['title'],
            'description': description_text,
            'tags': metadata['tags'],
            'categoryId': '23' # Comedy
        },
        'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}
    }

    media = MediaFileUpload("final_short.mp4", chunksize=-1, resumable=True)
    request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
    response = request.execute()
    print(f"✅ ВИДЕО ОПУБЛИКОВАНО! ID: {response['id']}")

if __name__ == "__main__":
    print("1. Генерируем сценарий...")
    data = get_script()
    
    print("2. Озвучиваем...")
    asyncio.run(create_audio(data['text']))
    
    print("3. Скачиваем фон...")
    download_pexels_video(data['query'])
    
    print("4. Собираем видео с субтитрами...")
    build_video(data['text'])
    
    print("5. Загружаем на YouTube...")
    upload_to_youtube(data)
