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

# Меняем модель на deepseek/deepseek-chat (более стабильная и бесплатная/дешевая)
OPENROUTER_MODEL = "deepseek/deepseek-chat" 

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
        "temperature": 0.3,
        "max_tokens": 1000
    }
    try:
        response = await asyncio.to_thread(requests.post, "https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=60)
        
        # Если статус не 200, значит, есть ошибка от OpenRouter
        if response.status_code != 200:
            logging.error(f"OpenRouter returned non-200 status: {response.status_code} - {response.text}")
            return None

        res_json = response.json()
        
        # Проверяем наличие ключа 'choices'
        if not res_json or "choices" not in res_json or not res_json["choices"]:
            logging.error(f"OpenRouter response missing 'choices' or it's empty: {res_json}")
            return None

        content = res_json["choices"][0]["message"]["content"].strip()
        
        # Убедимся, что это JSON, даже если модель добавила ```json
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()
            
        return json.loads(content).get("dot_code")
    except json.JSONDecodeError as e:
        logging.error(f"Failed to decode JSON from AI response: {content} Error: {e}")
        return None
    except Exception as e:
        logging.error(f"General AI Error: {e}")
        return None

def get_infographic_url(dot_code):
    styled_dot = dot_code.replace('digraph G {', 'digraph G { \n  bgcolor="transparent"; \n  node [fontname="Arial", fontsize=12, shape=rect, style="rounded,filled", fillcolor="#E3F2FD", color="#2196F3", penwidth=2, margin=0.3]; \n  edge [color="#1976D2", penwidth=1.5, arrowhead=vee];')
    encoded = urllib.parse.quote(styled_dot.strip())
    return f"https://quickchart.io/graphviz?format=png&width=1024&height=1024&graph={encoded}"

@dp.message(Command("start"))
async def cmd_start(msg: types.Message):
    await msg.answer("🎨 **Пришлите тему или текст для создания инфографики.**")

@dp.message(F.text)
async def handle_text(msg: types.Message):
    status_msg = await msg.answer("🚀 **Создаю дизайн...**")

    prompt = f"""
    Create a professional, high-quality infographic code in Graphviz (DOT) for the topic: "{msg.text}".
    Requirements:
    - Language: RUSSIAN.
    - Structure: Deep and logical (7-10 nodes), representing key concepts and relationships.
    - Design: Professional hierarchy.
    - Return ONLY JSON: {{"dot_code": "digraph G {{ ... }}"}}
    """

    dot_code = await generate_ai_logic(prompt)
    
    if not dot_code:
        await status_msg.edit_text("❌ Ошибка ИИ. Возможно, лимиты исчерпаны или неверный ключ. Попробуйте еще раз.")
        return

    img_url = get_infographic_url(dot_code)
    
    try:
        await bot.send_photo(
            msg.chat.id, 
            photo=img_url, 
            caption=f"✅ **Инфографика по теме:** {msg.text[:50]}..."
        )
        await status_msg.delete()
    except Exception as e:
        logging.error(f"Visualization error: {e}")
        await status_msg.edit_text("❌ Ошибка визуализации. Возможно, ИИ сгенерировал неверный DOT-код. Попробуйте более простую тему.")

async def main():
    port = int(os.getenv("PORT", 10000))
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port))
    await asyncio.gather(server.serve(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())
