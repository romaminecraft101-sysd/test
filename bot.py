import os
import io
import json
import asyncio
import textwrap
from aiohttp import web

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import BufferedInputFile

from PIL import Image, ImageDraw, ImageFont
from google import genai

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Загрузка шрифтов с кириллицей разных размеров
FONT_PATH = "Roboto-Regular.ttf"

def get_font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        print("Предупреждение: Шрифт не найден, используется стандартный")
        return ImageFont.load_default()

# --- Улучшенный промпт для инфографики ---
SYSTEM_PROMPT = """
Ты — профессиональный UI/UX дизайнер и создатель инфографики. Твоя задача — составить подробную JSON-конфигурацию макета (1000x800 px) на основе запроса пользователя.

Верни ТОЛЬКО валидный JSON со следующей структурой (без маркдауна и разметки ```json):
{
  "bg_color": "HEX цвет фона (напр. #0b0d17)",
  "shapes": [
    {
      "type": "rectangle" | "circle" | "line",
      "coords": [x1, y1, x2, y2],
      "color": "HEX цвет",
      "width": 2 (для линий)
    }
  ],
  "texts": [
    {
      "text": "Текст (на русском)",
      "x": 100,
      "y": 100,
      "color": "HEX цвет",
      "size": 24 (размер: 32 для заголовков, 18-22 для подписей),
      "max_width": 30 (символов в строке для автопереноса)
    }
  ]
}

Правила инфографики:
1. Используй гармоничную темную или светлую схему.
2. Делай 1 главный крупный элемент в центре и 3-5 выносных блоков с подписями и соединительными линиями (type: "line").
3. Обязательно добавляй главный заголовок вверху макета (size: 32-36).
"""

# --- Функция отрисовки инфографики ---
def draw_image_from_config(config: dict) -> bytes:
    # Увеличиваем разрешение до 1000x800 для более детальной схемы
    img = Image.new("RGB", (1000, 800), color=config.get("bg_color", "#0b0d17"))
    draw = ImageDraw.Draw(img)

    # 1. Рисуем фигуры и линии
    for shape in config.get("shapes", []):
        stype = shape.get("type")
        coords = shape.get("coords", [0, 0, 100, 100])
        color = shape.get("color", "#ffffff")
        width = shape.get("width", 2)

        if stype == "rectangle":
            draw.rectangle(coords, fill=color)
        elif stype == "circle":
            draw.ellipse(coords, fill=color)
        elif stype == "line":
            draw.line(coords, fill=color, width=width)

    # 2. Рисуем текст с переносами и шрифтом
    for text_info in config.get("texts", []):
        raw_text = text_info.get("text", "")
        x = text_info.get("x", 50)
        y = text_info.get("y", 50)
        color = text_info.get("color", "#ffffff")
        size = text_info.get("size", 20)
        max_width = text_info.get("max_width", 35)

        font = get_font(size)

        # Автоперенос длинных строк
        wrapped_lines = textwrap.wrap(raw_text, width=max_width)
        
        current_y = y
        for line in wrapped_lines:
            draw.text((x, current_y), line, fill=color, font=font)
            current_y += size + 4  # Межстрочный интервал

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.getvalue()


# --- Обработчики команд ---
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer(
        "Привет! Я создаю схемы и инфографику по твоему запросу.\n\n"
        "Напиши тему, например: *'Как устроена черная дыра'* или *'Строение атома'*"
    )

@dp.message(F.text)
async def generate_custom_image(message: types.Message):
    if not ai_client:
        await message.answer("❌ Ошибка: Ключ GEMINI_API_KEY не задан!")
        return

    user_prompt = message.text
    status_msg = await message.answer("📊 Генерирую схему инфографики через Gemini AI...")

    try:
        response = ai_client.models.generate_content(
            model="gemini-3.6-flash",
            contents=f"{SYSTEM_PROMPT}\n\nЗапрос пользователя: {user_prompt}"
        )
        
        raw_json = response.text.replace("```json", "").replace("```", "").strip()
        config = json.loads(raw_json)

        png_bytes = draw_image_from_config(config)
        photo = BufferedInputFile(png_bytes, filename="infographic.png")

        await status_msg.delete()
        await message.answer_photo(photo, caption=f"Инфографика: *{user_prompt}*")

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка генерации: {str(e)}")


# --- Заглушка веб-сервера ---
async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def main():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
