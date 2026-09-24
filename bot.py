import os
import asyncio
import logging
import urllib.parse
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
OPENROUTER_MODEL = "deepseek/deepseek-chat"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()
app = FastAPI()

user_formats = {}

@app.get("/health")
async def health():
    return {"status": "ok"}

async def generate_prompt_with_llm(user_topic: str) -> str:
    """Генерирует короткий и емкий английский промпт через DeepSeek."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "system", 
                "content": "You are a prompt engineer for AI image generators (FLUX/Stable Diffusion). Output ONLY a concise English image prompt without conversational text, introduction, or formatting markdown."
            },
            {
                "role": "user", 
                "content": f"Create a high quality image prompt for an infographic poster about: '{user_topic}'. Style: vector infographic, modern design, dark theme, crisp typography, 8k resolution, graphic design."
            }
        ],
        "temperature": 0.5,
        "max_tokens": 150
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
            if res.status_code == 200:
                data = res.json()
                return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logging.error(f"Error expanding prompt with LLM: {e}")
    
    return f"Infographic poster design about {user_topic}, vector design, dark background, highly detailed"

async def generate_image_pollinations(prompt: str, width: int, height: int) -> bytes:
    """Генерация изображения через Pollinations AI (Flux model)."""
    encoded_prompt = urllib.parse.quote(prompt)
    # Используем проверенный публичный сервис без авторизации
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&model=flux&seed=42&nologo=true"
    
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code != 200:
                logging.error(f"Pollinations error status {response.status_code}")
                return None
            return response.content
    except Exception as e:
        logging.error(f"Image fetch error: {e}")
        return None

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

    image_prompt = await generate_prompt_with_llm(msg.text)
    logging.info(f"Generated prompt: {image_prompt}")

    await status_msg.edit_text("🎨 **Нейросеть генерирует изображение...**")

    image_bytes = await generate_image_pollinations(
        prompt=image_prompt,
        width=current_format["width"],
        height=current_format["height"]
    )

    if not image_bytes:
        await status_msg.edit_text("❌ Ошибка генерации. Попробуйте еще раз.")
        return

    try:
        document_file = BufferedInputFile(image_bytes, filename="infographic_art.png")

        await bot.send_document(
            msg.chat.id, 
            document=document_file, 
            caption=f"✅ **Ваша арт-инфографика без сжатия:** {msg.text[:50]}..."
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
