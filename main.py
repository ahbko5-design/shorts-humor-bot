import os
import json
import time
import random
import requests
import asyncio
import urllib.parse
from google import genai
import edge_tts

try:
    from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip, CompositeAudioClip, concatenate_videoclips
except ImportError:
    from moviepy.video.VideoClip import ImageClip
    from moviepy.audio.io.AudioFileClip import AudioFileClip
    from moviepy.video.VideoClip import TextClip
    from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
    from moviepy.audio.AudioClip import CompositeAudioClip
    from moviepy.video.compositing.concatenate import concatenate_videoclips

import google_auth_oauthlib.flow
import googleapiclient.discovery
from googleapiclient.http import MediaFileUpload

# 1. Проверка секретов
if not os.path.exists('client_secret.json'):
    with open('client_secret.json', 'w') as f:
        f.write(os.getenv('CLIENT_SECRET_JSON', ''))

if not os.path.exists('token.json'):
    with open('token.json', 'w') as f:
        f.write(os.getenv('YOUTUBE_TOKEN', ''))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

VIRAL_MEME_PRESETS = [
    {"topic": "Senior Dev vs Junior Dev in Code Review", "animal": "cute fluffy Pixar cat"},
    {"topic": "Deploying code on Friday at 5 PM", "animal": "Pixar style dog wearing hoodie"},
    {"topic": "Fixing 1 bug creates 10 new bugs", "animal": "panicking Pixar style cat programmer"},
    {"topic": "Trying to center a div with CSS", "animal": "crazy funny 3D Pixar dog at computer"},
    {"topic": "Client asking for a quick small change", "animal": "crying Pixar cat sitting at laptop desk"},
    {"topic": "Code worked locally but failed in production", "animal": "shocked 3D Pixar dog with glasses"}
]

# Прямые ссылки на бесплатную фоновую мемную музыку / звуковые эффекты
BG_MUSIC_URLS = [
    "https://actions.google.com/sounds/v1/cartoon/cartoon_boing.ogg",
    "https://actions.google.com/sounds/v1/cartoon/clown_horn.ogg",
    "https://actions.google.com/sounds/v1/cartoon/pop.ogg"
]

def get_script():
    client = genai.Client(api_key=GEMINI_API_KEY)
    preset = random.choice(VIRAL_MEME_PRESETS)
    
    prompt = f"""
    Write a short, highly relatable IT meme voiceover script based on this joke format:
    TOPIC: {preset['topic']}.
    ANIMAL CHARACTER: {preset['animal']}.
    
    Guidelines:
    - Keep it under 12-15 seconds.
    - Highly relatable, hilarious developer life moment.
    - End with: "Subscribe to Tech Humor Lab for daily IT laughs!"
    
    Return ONLY a JSON object:
    {{
      "text": "The spoken voiceover text without emojis",
      "image_prompts": [
        "A 3D Pixar style cute fluffy cat wearing a hoodie sitting at laptop computer in programmer office, highly detailed 8k render, octane render", 
        "A 3D Pixar style cute dog looking shocked and stressed at computer screen with code, vibrant lighting, highly detailed", 
        "A 3D Pixar style cat facepalm holding head at desk near laptop, funny meme expression, 8k"
      ],
      "title": "{preset['topic']} 💀 #shorts #ithumor #programming #devlife #pixar",
      "tags": ["TechHumor", "ProgrammingMemes", "Coding", "DeveloperLife", "Shorts", "Pixar", "Animation"]
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
                raw_text = raw_text.split("
