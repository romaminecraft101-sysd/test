import os
import asyncio
import logging
import json
import httpx
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile

from fastapi import FastAPI
import uvicorn

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
HF_TOKEN = os.getenv("HF_TOKEN", "").strip()

OPENROUTER_MODEL = "deepseek/deepseek-chat"

# Используем быстрый и качественный FLUX.1-schnell от Black Forest Labs
HF_MODEL_URL = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()
app = FastAPI()

user_formats = {}

@app.get("/health")
async def health():
    return {"status": "ok"}

async def generate_prompt_with_llm(user_topic: str) -> str:
    """Использует DeepSeek для составления детального англоязычного промпта под инфографику."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "system", 
                "content": "You are an expert AI art prompt creator specializing in infographics, modern UI diagrams, and futuristic educational posters. Convert user request into a highly detailed English image generation prompt."
            },
            {
                "role": "user", 
                "content": f"Create a detailed text-to-image prompt in English for a visual infographic about: '{user_topic}'. Include style notes: clean layout, vector design, high contrast, 3D elements, dark slate blue background, modern typography icons, trending on Dribbble, extremely detailed, 8k resolution."
            }
        ],
        "temperature": 0.6,
        "max_tokens": 300
    }
    
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            res = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
            if res.status_code == 200:
                data = res.json()
                return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logging.error(f"Error expanding prompt with LLM: {e}")
    
    # Резервный промпт, если LLM не ответила
    return f"Modern sleek infographic design about {user_topic}, clean vector layout, dark mode, high quality 8k, detailed icons, modern graphics, 3d rendered elements"

async def generate_image_huggingface(prompt: str, width: int, height: int) -> bytes:
    """Отправляет запрос в Hugging Face Inference API и возвращает байты изображения."""
    headers = {
        "Authorization": f"Bearer {HF_TOKEN}" if HF_TOKEN else "",
        "Content-Type": "application/json"
    }
    
    payload = {
        "inputs": prompt,
        "parameters": {
            "width": width,
            "height": height
        }
    }
    
    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(HF_MODEL_URL, headers=headers, json=payload)
        
        if response.status_code != 200:
            logging.error(f"HuggingFace Error {response.status_code}: {response.text}")
            return None
            
        return response.content

@dp.message(Command("start"))
async def cmd_start(msg: types.Message):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="1:1 (Квадрат)", callback_data="format_1024_1024")],
        [types.InlineKeyboardButton(text="16:9 (Горизонтальный)", callback_data="format_1024_576")],
        [types.InlineKeyboardButton(text="9:16 (Вертикальный)", callback_data="format_576_1024")]
    ])
    await msg.answer("🎨 **Выберите формат изображения:**", reply_markup=kb)

@dp.callback_query(F.data.startswith("format_"))
async def set_format_callback(callback: types.CallbackQuery):
    parts = callback.data.split('_')
    width_str, height_str = parts[1], parts[2]
    
    user_id = callback.from_user.id
    user_formats[user_id] = {"width": int(width_str), "height": int(height_str)}
    
    await callback.message.edit_text(
        f"✅ Формат установлен на **{width_str}x{height_str}**.\nПришлите тему для генерации.",
        reply_markup=None
    )
    await callback.answer("Формат установлен.", show_alert=False)

@dp.message(F.text)
async def handle_text(msg: types.Message):
    user_id = msg.from_user.id
    current_format = user_formats.get(user_id, {"width": 1024, "height": 1024})

    status_msg = await msg.answer("🧠 **Составляю детализированный арт-промпт...**")

    # 1. Генерируем расширенный промпт через DeepSeek
    image_prompt = await generate_prompt_with_llm(msg.text)
    logging.info(f"Generated prompt: {image_prompt}")

    await status_msg.edit_text("🎨 **Нейросеть генерирует изображение (HuggingFace)...**")

    # 2. Генерируем картинку через FLUX/HF
    image_bytes = await generate_image_huggingface(
        prompt=image_prompt,
        width=current_format["width"],
        height=current_format["height"]
    )

    if not image_bytes:
        await status_msg.edit_text("❌ Ошибка генерации изображения. Модель временно перегружена или заблокирована. Попробуйте снова.")
        return

    try:
        # 3. Отправляем документ без сжатия
        document_file = BufferedInputFile(image_bytes, filename="generated_art.png")

        await bot.send_document(
            msg.chat.id, 
            document=document_file, 
            caption=f"✅ **Ваша арт-инфографика:** {msg.text[:50]}..."
        )
        await status_msg.delete()
    except Exception as e:
        logging.error(f"Telegram upload error: {e}")
        await status_msg.edit_text("❌ Ошибка при отправке файла в Telegram.")

async def main():
    port = int(os.getenv("PORT", 10000))
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port))
    await asyncio.gather(server.serve(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())
