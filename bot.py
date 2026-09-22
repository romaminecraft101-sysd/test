import os
import io
import json
import asyncio
from aiohttp import web

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import BufferedInputFile

from PIL import Image, ImageDraw, ImageFont
from google import genai

# Получаем переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Инициализируем клиент Gemini только если ключ передан
ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# ... далее остальной код ...
