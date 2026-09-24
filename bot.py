import os
import asyncio
import urllib.parse
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

OPENROUTER_MODEL = "deepseek/deepseek-chat"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()
app = FastAPI()

user_formats = {}

@app.get("/health")
async def health():
    return {"status": "ok"}

async def generate_ai_logic(prompt: str):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "system", 
                "content": "You are an elite infographic and Graphviz DOT architect. You generate visually rich, complex, modern-styled Graphviz diagrams using subgraphs, clusters, gradient-like dark palettes, HTML-like labels, and emoji icons. You output ONLY valid JSON."
            },
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.4,
        "max_tokens": 2000
    }
    
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload
            )
        
        if response.status_code != 200:
            logging.error(f"OpenRouter status: {response.status_code} - {response.text}")
            return None

        res_json = response.json()
        if not res_json or "choices" not in res_json or not res_json["choices"]:
            logging.error(f"OpenRouter empty choices: {res_json}")
            return None

        content = res_json["choices"][0]["message"]["content"].strip()
        
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].strip().startswith("```"): 
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"): 
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        data = json.loads(content)
        return data.get("dot_code")

    except Exception as e:
        logging.error(f"General AI Error: {e}")
        return None

def get_infographic_url(dot_code: str, width: int = 1024, height: int = 1024) -> str:
    # Темный фоновый пресет с закругленными блоками и современной типографикой
    style_injection = (
        'digraph G { \n'
        '  bgcolor="#0F172A"; \n'
        '  pad="0.8"; \n'
        '  rankdir="TB"; \n'
        '  graph [fontname="Helvetica", fontsize=16, fontcolor="#F8FAFC", nodesep="0.6", ranksep="0.8", splines="ortho", compound=true]; \n'
        '  node [fontname="Helvetica", fontsize=11, fontcolor="#F8FAFC", shape="rect", style="filled,rounded", fillcolor="#1E293B", color="#38BDF8", penwidth=2, margin="0.3,0.2"]; \n'
        '  edge [fontname="Helvetica", fontsize=9, fontcolor="#94A3B8", color="#38BDF8", penwidth=2, arrowhead="vee", arrowsize=1.2]; \n'
    )
    
    styled_dot = dot_code.replace('digraph G {', style_injection)
    encoded = urllib.parse.quote(styled_dot.strip())
    return f"[https://quickchart.io/graphviz?format=png&width=](https://quickchart.io/graphviz?format=png&width=){width}&height={height}&graph={encoded}"

@dp.message(Command("start"))
async def cmd_start(msg: types.Message):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="1:1 (Квадрат)", callback_data="format_1024_1024")],
        [types.InlineKeyboardButton(text="16:9 (Горизонтальный)", callback_data="format_1920_1080")],
        [types.InlineKeyboardButton(text="9:16 (Вертикальный)", callback_data="format_1080_1920")]
    ])
    await msg.answer("🎨 **Выберите формат инфографики:**", reply_markup=kb)

@dp.callback_query(F.data.startswith("format_"))
async def set_format_callback(callback: types.CallbackQuery):
    parts = callback.data.split('_')
    width_str, height_str = parts[1], parts[2]
    
    user_id = callback.from_user.id
    user_formats[user_id] = {"width": int(width_str), "height": int(height_str)}
    
    await callback.message.edit_text(
        f"✅ Формат инфографики установлен на **{width_str}x{height_str}**.\nПришлите тему или текст.",
        reply_markup=None
    )
    await callback.answer("Формат установлен.", show_alert=False)

@dp.message(F.text)
async def handle_text(msg: types.Message):
    user_id = msg.from_user.id
    current_format = user_formats.get(user_id, {"width": 1024, "height": 1024})

    status_msg = await msg.answer("🚀 **Создаю насыщенный дизайн и графику...**")

    prompt = f"""
    Create a detailed, feature-rich, high-density infographic in Graphviz (DOT) for the topic: "{msg.text}".
    
    Design Rules:
    1. Language: RUSSIAN.
    2. Structural richness:
       - Use clusters (`subgraph cluster_name {{ label="..."; ... }}`) to visually group related modules.
       - Create 10 to 16 nodes with distinct functions.
       - Use meaningful Emojis in labels for visual interest (e.g. 🚀, 💡, ⚡, 🔍, 📊, 🛡️).
       - Add descriptive edge labels to explain relationships.
    3. Styling:
       - Use different fillcolor accents for nodes based on importance (e.g., `#0EA5E9` for main, `#8B5CF6` for sub-processes, `#10B981` for results).
       - Ensure syntax is strictly valid Graphviz DOT.
    4. Format:
       - Return ONLY JSON in format: {{"dot_code": "digraph G {{ ... }}"}}
    """

    dot_code = await generate_ai_logic(prompt)
    
    if not dot_code:
        await status_msg.edit_text("❌ Ошибка ИИ. Не удалось сгенерировать структуру.")
        return

    img_url = get_infographic_url(dot_code, current_format["width"], current_format["height"])
    
    try:
        # Скачиваем изображение в память для отправки как оригинальный файл без сжатия
        async with httpx.AsyncClient(timeout=30.0) as client:
            img_res = await client.get(img_url)
            if img_res.status_code != 200:
                raise Exception(f"QuickChart returned status {img_res.status_code}")
            image_bytes = img_res.content

        document_file = BufferedInputFile(image_bytes, filename="infographic_hd.png")

        # Отправляем документом (без сжатия качества)
        await bot.send_document(
            msg.chat.id, 
            document=document_file, 
            caption=f"🎨 **Ваша инфографика без сжатия:** {msg.text[:50]}..."
        )
        await status_msg.delete()
    except Exception as e:
        logging.error(f"Visualization error: {e}")
        await status_msg.edit_text("❌ Ошибка сгенерированной визуализации. Попробуйте сформулировать тему иначе.")

async def main():
    port = int(os.getenv("PORT", 10000))
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port))
    await asyncio.gather(server.serve(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())
