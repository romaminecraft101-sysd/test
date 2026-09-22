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

# Переменные окружения из панели Render
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Безопасная инициализация клиента Gemini (бот не упадет, если ключа нет)
ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# --- Промпт для генерации структуры дизайна ---
SYSTEM_PROMPT = """
Ты — AI-дизайнер. Твоя задача — составить JSON-конфигурацию для создания баннера/картинки (800x600 px) на основе запроса пользователя.

Верни ТОЛЬКО валидный JSON со следующей структурой (без маркдауна и разметки ```json):
{
  "bg_color": "HEX цвет фона (например #ffffff)",
  "shapes": [
    {
      "type": "rectangle" или "circle",
      "coords": [x1, y1, x2, y2] (в пределах 800x600),
      "color": "HEX цвет фигуры"
    }
  ],
  "texts": [
    {
      "text": "Текст для отображения (кратко)",
      "x": 220,
      "y": 140,
      "color": "HEX цвет текста"
    }
  ]
}
Создавай красивую композицию из 2-4 фигур и 1-3 текстов, сочетая гармоничные цвета.
"""

# --- Функция отрисовки PNG по JSON-конфигурации ---
def draw_image_from_config(config: dict) -> bytes:
    img = Image.new("RGB", (800, 600), color=config.get("bg_color", "#ffffff"))
    draw = ImageDraw.Draw(img)

    # 1. Рисуем фигуры
    for shape in config.get("shapes", []):
        stype = shape.get("type")
        coords = shape.get("coords", [0, 0, 100, 100])
        color = shape.get("color", "#000000")

        if stype == "rectangle":
            draw.rectangle(coords, fill=color)
        elif stype == "circle":
            draw.ellipse(coords, fill=color)

    # 2. Рисуем текст
    font = ImageFont.load_default()
    for text_info in config.get("texts", []):
        text = text_info.get("text", "")
        x = text_info.get("x", 50)
        y = text_info.get("y", 50)
        color = text_info.get("color", "#000000")
        
        draw.text((x, y), text, fill=color, font=font)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.getvalue()


# --- Обработчики команд бота ---
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer(
        "Привет! Напиши мне тему или описание картинки, и я сгенерирую подходящий макет из фигур и текста.\n\n"
        "Например: *'Реклама скидок в магазине одежды'* или *'Открытка с днём рождения'*"
    )

@dp.message(F.text)
async def generate_custom_image(message: types.Message):
    if not ai_client:
        await message.answer("❌ Ошибка: Ключ GEMINI_API_KEY не задан в переменных окружения Render!")
        return

    user_prompt = message.text
    status_msg = await message.answer("🎨 Продумываю дизайн с помощью Gemini AI...")

    try:
        # Запрос к Gemini
        response = ai_client.models.generate_content(
            model="gemini-3.6-flash",
            contents=f"{SYSTEM_PROMPT}\n\nЗапрос пользователя: {user_prompt}"
        )
        
        # Очищаем ответ от маркдаун-разметки, если модель её добавит
        raw_json = response.text.replace("```json", "").replace("```", "").strip()
        config = json.loads(raw_json)

        # Рисуем изображение
        png_bytes = draw_image_from_config(config)
        photo = BufferedInputFile(png_bytes, filename="design.png")

        await status_msg.delete()
        await message.answer_photo(photo, caption=f"Вот ваш макет на тему: *{user_prompt}*")

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка при генерации дизайна: {str(e)}")


# --- Веб-сервер заглушка для Render (чтобы открылся порт) ---
async def handle_ping(request):
    return web.Response(text="Bot with web-port is running fine!")

async def main():
    # Запускаем фоновый HTTP-сервер для проверки работоспособности в Render
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    print(f"Заглушка веб-сервера запущена на порту {port}...")
    print("Запускаем Long Polling бота...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
