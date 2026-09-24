import os
import asyncio
import urllib.parse
import logging
import requests
import json
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from fastapi import FastAPI
import uvicorn

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = "google/gemini-2.0-flash-001" # Модель, которая лучше всех пишет код

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()
app = FastAPI()

@app.get("/health")
async def health(): return {"status": "ok"}

async def generate_ai_logic(prompt):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": "You are a professional designer. You output ONLY valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.3
    }
    try:
        response = await asyncio.to_thread(requests.post, "https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=60)
        res_json = response.json()
        content = res_json["choices"][0]["message"]["content"].strip()
        return json.loads(content).get("dot_code")
    except Exception as e:
        logging.error(f"AI Error: {e}")
        return None

def get_infographic_url(dot_code):
    # Настройки профессионального стиля
    styled_dot = dot_code.replace('digraph G {', 'digraph G { \n  bgcolor="transparent"; \n  node [fontname="Arial", fontsize=12, shape=rect, style="rounded,filled", fillcolor="#E3F2FD", color="#2196F3", penwidth=2, margin=0.3]; \n  edge [color="#1976D2", penwidth=1.5, arrowhead=vee];')
    encoded = urllib.parse.quote(styled_dot.strip())
    # Генерируем PNG (картинку), а не PDF для удобства
    return f"https://quickchart.io/graphviz?format=png&width=1024&height=1024&graph={encoded}"

@dp.message(Command("start"))
async def cmd_start(msg: types.Message):
    await msg.answer("🎨 **Пришлите тему или текст для создания инфографики.**")

@dp.message(F.text)
async def handle_text(msg: types.Message):
    # 1. Сразу удаляем сообщение пользователя, если хотим идеальной чистоты (опционально)
    # await msg.delete() 
    
    status_msg = await msg.answer("🚀 **Создаю дизайн...**")

    prompt = f"""
    Create a professional, high-quality infographic code in Graphviz (DOT) for the topic: "{msg.text}".
    Requirements:
    - Language: RUSSIAN.
    - Structure: Deep and logical (7-10 nodes).
    - Design: Professional hierarchy.
    - Return ONLY JSON: {{"dot_code": "digraph G {{ ... }}"}}
    """
    dot_code = await generate_ai_logic(prompt)
    
    if not dot_code:
        await status_msg.edit_text("❌ Ошибка ИИ. Попробуйте еще раз.")
        return

    img_url = get_infographic_url(dot_code)
    
    try:
        # Отправляем как фото (PNG)
        await bot.send_photo(
            msg.chat.id, 
            photo=img_url, 
            caption=f"✅ **Инфографика по теме:** {msg.text[:50]}..."
        )
        # 2. Удаляем сервисное сообщение "Создаю дизайн", чтобы не было каши
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text("❌ Ошибка визуализации. Попробуйте более простую тему.")

async def main():
    port = int(os.getenv("PORT", 10000))
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port))
    await asyncio.gather(server.serve(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())
