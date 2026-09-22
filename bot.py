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
from openai import OpenAI

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Клиент OpenAI, настроенный под OpenRouter
ai_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
) if OPENROUTER_API_KEY else None

FONT_PATH = "Roboto-Regular.ttf"

def get_font(size: int):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()

SYSTEM_PROMPT = """
Ты — арт-директор и ведущий UI/UX дизайнер. Твоя задача — составить богатую, эстетичную JSON-конфигурацию премиальной инфографики (1200x900 px) по запросу пользователя.

Верни ТОЛЬКО валидный JSON (без маркдауна, текста вокруг и разметки ```json):
{
  "gradient_bg": {
    "start_color": "#0f172a",
    "end_color": "#1e1b4b"
  },
  "cards": [
    {
      "coords": [50, 160, 380, 480],
      "bg_color": "#1e293b",
      "border_color": "#3b82f6",
      "radius": 16,
      "border_width": 2
    }
  ],
  "shapes": [
    {
      "type": "circle" | "line" | "badge",
      "coords": [x1, y1, x2, y2],
      "color": "#6366f1",
      "width": 3
    }
  ],
  "texts": [
    {
      "text": "Текст блока",
      "x": 70,
      "y": 180,
      "color": "#ffffff",
      "size": 24,
      "max_width": 26
    }
  ]
}

Правила верстки:
1. Используй стильную темную тему (Slate, Indigo, Dark Blue).
2. Наверху выдели 1 КРУПНЫЙ Главный Заголовок (size: 36, y: 50).
3. Размести 4-6 структурированных блоков-карточек (cards) с контентом.
4. Добавь соединительные линии (type: "line") для наглядности.
"""

def create_gradient(width: int, height: int, start_color: str, end_color: str) -> Image.Image:
    base = Image.new("RGB", (width, height), start_color)
    top = Image.new("RGB", (width, height), end_color)
    mask = Image.new("L", (width, height))
    
    for y in range(height):
        alpha = int(255 * (y / height))
        for x in range(width):
            mask.putpixel((x, y), alpha)
            
    base.paste(top, (0, 0), mask)
    return base

def draw_advanced_infographic(config: dict) -> bytes:
    width, height = 1200, 900
    
    gbg = config.get("gradient_bg", {})
    img = create_gradient(
        width, height, 
        gbg.get("start_color", "#0f172a"), 
        gbg.get("end_color", "#1e1b4b")
    )
    draw = ImageDraw.Draw(img)

    for card in config.get("cards", []):
        coords = card.get("coords", [50, 50, 300, 200])
        bg_col = card.get("bg_color", "#1e293b")
        border_col = card.get("border_color", "#3b82f6")
        radius = card.get("radius", 14)
        b_width = card.get("border_width", 2)

        draw.rounded_rectangle(coords, radius=radius, fill=bg_col, outline=border_col, width=b_width)

    for shape in config.get("shapes", []):
        stype = shape.get("type")
        coords = shape.get("coords", [0, 0, 50, 50])
        color = shape.get("color", "#6366f1")
        w = shape.get("width", 2)

        if stype == "circle":
            draw.ellipse(coords, fill=color)
        elif stype == "line":
            draw.line(coords, fill=color, width=w)
        elif stype == "badge":
            draw.rounded_rectangle(coords, radius=6, fill=color)

    for text_info in config.get("texts", []):
        raw_text = text_info.get("text", "")
        x = text_info.get("x", 50)
        y = text_info.get("y", 50)
        color = text_info.get("color", "#ffffff")
        size = text_info.get("size", 20)
        max_w = text_info.get("max_width", 30)

        font = get_font(size)
        wrapped_lines = textwrap.wrap(raw_text, width=max_w)
        
        current_y = y
        for line in wrapped_lines:
            draw.text((x, current_y), line, fill=color, font=font)
            current_y += size + 6

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.getvalue()


@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer(
        "👋 Привет! Я создаю инфографику и графические схемы.\n\n"
        "Напиши тему, например: *'История и эволюция языков программирования'*"
    )

@dp.message(F.text)
async def generate_custom_image(message: types.Message):
    if not ai_client:
        await message.answer("❌ Ошибка: Переменная OPENROUTER_API_KEY не задана на Render!")
        return

    user_prompt = message.text
    status_msg = await message.answer("🎨 Проектирую макет схемы...")

    try:
        completion = await asyncio.to_thread(
            ai_client.chat.completions.create,
            model="meta-llama/llama-3.3-70b-instruct:free",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Создай инфографику на тему: {user_prompt}"}
            ],
            temperature=0.2
        )

        raw_json = completion.choices[0].message.content
        # Очистка JSON от случайных тегов
        raw_json = raw_json.replace("```json", "").replace("```", "").strip()
        config = json.loads(raw_json)

        png_bytes = await asyncio.to_thread(draw_advanced_infographic, config)
        photo = BufferedInputFile(png_bytes, filename="infographic.png")

        await status_msg.delete()
        await message.answer_photo(photo, caption=f"Инфографика: *{user_prompt}*")

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка генерации: {str(e)}")


async def handle_ping(request):
    return web.Response(text="Bot is running smoothly!")

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
