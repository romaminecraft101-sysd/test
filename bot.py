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
# Llama 3 - очень сильная модель для кодинга и структурированного вывода
OPENROUTER_MODEL = "meta-llama/llama-3-8b-instruct" 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()
app = FastAPI()

# Словарь для хранения пользовательских настроек формата
# Key: user_id, Value: {"width": int, "height": int}
user_formats = {}

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
            {"role": "system", "content": "You are a professional infographic designer. You output ONLY valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.5, # Чуть выше температура для креатива в дизайне
        "max_tokens": 1200 # Больше токенов для сложной схемы
    }
    try:
        response = await asyncio.to_thread(requests.post, "https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=90) # Увеличим таймаут
        
        if response.status_code != 200:
            logging.error(f"OpenRouter returned non-200 status: {response.status_code} - {response.text}")
            return None

        res_json = response.json()
        if not res_json or "choices" not in res_json or not res_json["choices"]:
            logging.error(f"OpenRouter response missing 'choices' or it's empty: {res_json}")
            return None

        content = res_json["choices"][0]["message"]["content"].strip()
        
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].strip().startswith("```"): lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"): lines = lines[:-1]
            content = "\n".join(lines).strip()
            
        return json.loads(content).get("dot_code")
    except json.JSONDecodeError as e:
        logging.error(f"Failed to decode JSON from AI response: {content} Error: {e}")
        return None
    except Exception as e:
        logging.error(f"General AI Error: {e}")
        return None

def get_infographic_url(dot_code, width=1024, height=1024):
    # Ультра-профессиональный стиль Graphviz: градиентный фон, тени, объемные узлы
    # Используем более контрастные цвета и тени для глубины
    
    # Можно попробовать разные темы QuickChart: 'emerald', 'sky', 'material', 'grape'
    theme_name = "grape" # Очень красивый фиолетовый градиент
    
    # Добавляем стиль для узлов и ребер: тени, красивые цвета, разные формы
    styled_dot = dot_code.replace('digraph G {', 
                                  f'digraph G {{ \n  bgcolor="transparent"; \n  node [fontname="Arial", fontsize=14, shape=box, style="rounded,filled,drop_shadow", fillcolor="#9C27B0", color="#E0BBE4", fontcolor="#FFFFFF", penwidth=2, margin=0.4]; \n  edge [color="#8E24AA", penwidth=1.5, arrowhead=vee]; \n  graph [pad="0.5", nodesep="0.6", ranksep="0.7", fontname="Arial", fontsize=18, overlap=false, splines=true];')
    
    # Дополнительная кастомизация для узлов (если ИИ генерирует разные типы узлов)
    # Пример: node [shape=ellipse, style="filled", fillcolor="orange"];
    # Мы просим ИИ генерировать разные формы, и QuickChart это учтет.
    
    encoded = urllib.parse.quote(styled_dot.strip())
    
    return f"https://quickchart.io/graphviz?format=png&theme={theme_name}&width={width}&height={height}&graph={encoded}"

@dp.message(Command("start"))
async def cmd_start(msg: types.Message):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="1:1 (Квадрат)", callback_data="set_format_1024_1024")],
        [types.InlineKeyboardButton(text="16:9 (Горизонтальный)", callback_data="set_format_1920_1080")],
        [types.InlineKeyboardButton(text="9:16 (Вертикальный)", callback_data="set_format_1080_1920")]
    ])
    await msg.answer("🎨 **Выберите формат инфографики:**", reply_markup=kb)

@dp.callback_query(F.data.startswith("set_format_"))
async def set_format_callback(callback: types.CallbackQuery):
    _, width_str, height_str = callback.data.split('_')
    user_id = callback.from_user.id
    user_formats[user_id] = {"width": int(width_str), "height": int(height_str)}
    
    # Удаляем клавиатуру и подтверждаем выбор
    await callback.message.edit_text(
        f"✅ Формат инфографики установлен на **{width_str}x{height_str}**.\nТеперь **пришлите тему или текст.**",
        reply_markup=None # Удаляем inline-клавиатуру
    )
    await callback.answer("Формат установлен.", show_alert=False) # Просто короткое уведомление

@dp.message(F.text)
async def handle_text(msg: types.Message):
    user_id = msg.from_user.id
    current_format = user_formats.get(user_id, {"width": 1024, "height": 1024}) # По умолчанию 1:1

    status_msg = await msg.answer("🚀 **Создаю дизайн...**")

    prompt = f"""
    Create a highly professional, visually appealing, and complex infographic code in Graphviz (DOT) for the topic: "{msg.text}".
    Requirements:
    - Language: RUSSIAN.
    - Structure: Deep, logical, and detailed (8-12 nodes). Use different node shapes (e.g., ellipses for starting/ending points, boxes for processes, diamonds for decisions).
    - Design: Advanced hierarchy, clear and distinct connections (e.g., solid for main, dashed for secondary).
    - Node colors and edge styles should reflect logical grouping or importance (e.g., main nodes green, sub-nodes blue, decision nodes yellow).
    - Ensure ALL Graphviz syntax is perfectly valid.
    - Return ONLY JSON: {{"dot_code": "digraph G {{ ... }}"}}
    """

    dot_code = await generate_ai_logic(prompt)
    
    if not dot_code:
        await status_msg.edit_text("❌ Ошибка ИИ. Возможно, лимиты исчерпаны или неверный ключ. Попробуйте еще раз с другой темой.")
        return

    img_url = get_infographic_url(dot_code, current_format["width"], current_format["height"])
    
    try:
        await bot.send_photo(
            msg.chat.id, 
            photo=img_url, 
            caption=f"✅ **Ваша профессиональная инфографика:** {msg.text[:50]}..."
        )
        await status_msg.delete()
    except Exception as e:
        logging.error(f"Visualization error: {e}")
        await status_msg.edit_text("❌ Ошибка визуализации. Возможно, ИИ сгенерировал неверный DOT-код или URL слишком длинный. Попробуйте более простую тему.")

async def main():
    port = int(os.getenv("PORT", 10000))
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port))
    await asyncio.gather(server.serve(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())
