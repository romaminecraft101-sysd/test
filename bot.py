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
BOT_TOKEN = os.getenv("BOT_TOKEN", "8916069792:AAHJYqH3NL42DpW4o-yA3vyN9B4gnuef8DI").strip()
HF_TOKEN = os.getenv("HF_TOKEN", "hf_ТВОЙ_КЛЮЧ_ЗДЕСЬ").strip()

# Используем быструю и стабильную модель Qwen через Inference API
HF_MODEL_URL = "https://api-inference.huggingface.co/models/Qwen/Qwen2.5-Coder-32B-Instruct"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---
app = FastAPI()

@app.get("/")
@app.get("/health")
async def health():
    return {"status": "ok", "bot": "AI Infographic Generator (HuggingFace API)"}

# --- ФУНКЦИЯ ВЫЗОВА HUGGING FACE ЧЕРЕЗ ЧИСТЫЙ REQUESTS (С UTF-8) ---
async def generate_hf_safe(prompt):
    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json; charset=utf-8"
    }
    
    payload = {
        "inputs": f"<|im_start|>system\nYou are a helpful assistant that strictly responds in JSON format.<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n",
        "parameters": {
            "max_new_tokens": 1000,
            "temperature": 0.2,
            "return_full_text": False
        }
    }

    def send_request():
        # Используем requests.post с явным указанием кодировки utf-8
        response = requests.post(HF_MODEL_URL, headers=headers, json=payload, timeout=60)
        return response

    try:
        response = await asyncio.to_thread(send_request)
        
        if response.status_code != 200:
            logging.error(f"HF API Error [{response.status_code}]: {response.text}")
            return None

        res_json = response.json()
        
        # Обработка ответа от Serverless API
        if isinstance(res_json, list) and len(res_json) > 0:
            content = res_json[0].get("generated_text", "").strip()
        elif isinstance(res_json, dict):
            content = res_json.get("generated_text", "").strip()
        else:
            content = str(res_json).strip()

        # Очистка от markdown ```json ... ```
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()
            
        return content
    except Exception as e:
        logging.error(f"Ошибка вызова Hugging Face API: {e}")
        return None

# --- ГЕНЕРАЦИЯ PDF-СХЕМЫ ЧЕРЕЗ QuickChart ---
def get_quickchart_pdf(dot_code, user_id):
    clean_code = dot_code.replace("```dot", "").replace("```", "").strip()
    encoded_code = urllib.parse.quote(clean_code)
    url = f"https://quickchart.io/graphviz?format=pdf&graph={encoded_code}"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при запросе к QuickChart: {e}")
        return None

    filename = f"infographic_{user_id}.pdf"
    with open(filename, "wb") as f:
        f.write(response.content)
    return filename

# --- ХЕНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(msg: types.Message):
    await msg.answer("🤖 **Привет! Я бот для создания инфографики (на базе Hugging Face).**\n\nПросто отправь мне любой текст (тему проекта, описание процесса, список идей), и я создам по нему схему-инфографику в формате PDF.")

@dp.message(F.text)
async def handle_user_text(msg: types.Message):
    user_text = msg.text
    status_msg = await msg.answer("⏳ **ИИ анализирует ваш текст и генерирует схему-инфографику...**")

    prompt = f"""
    На основе следующего текста:
    ---
    {user_text}
    ---
    Создай логическую схему (инфографику) в формате Graphviz (DOT). 
    Схема должна иметь:
    1. Направление сверху вниз (rankdir=TB).
    2. Узлы (nodes) формы 'box' (прямоугольники) со скругленными углами.
    3. Цвета: фон белый, узлы светло-голубые (lightblue), текст черный.
    4. Отрази 5-7 ключевых идей, этапов или связей из текста.
    5. Текст внутри блоков должен быть на РУССКОМ языке, кратким и понятным.
    
    Верни ответ СТРОГО в формате валидного JSON с одним ключом 'dot_code'.
    Пример ответа:
    {{
      "dot_code": "digraph G {{\\n  rankdir=TB;\\n  node [shape=box, style=\"rounded,filled\", fillcolor=\"lightblue\"];\\n  \\\"Начало\\\" -> \\\"Середина\\\";\\n  \\\"Середина\\\" -> \\\"Конец\\\";\\n}}"
    }}
    """

    ai_res = await generate_hf_safe(prompt)

    if not ai_res:
        await status_msg.edit_text("❌ ИИ-сервер временно не отвечает или модель загружается. Попробуйте еще раз через минуту.")
        return

    try:
        res_data = json.loads(ai_res)
        dot_code = res_data.get('dot_code')

        if not dot_code:
            await status_msg.edit_text("❌ ИИ не смог сгенерировать код схемы по вашему тексту. Попробуйте другой текст или тему.")
            return

        file_infographic = get_quickchart_pdf(dot_code, msg.from_user.id)

        if not file_infographic:
            await status_msg.edit_text("❌ Произошла ошибка при создании инфографики. Пожалуйста, попробуйте еще раз.")
            return

        await bot.send_document(msg.chat.id, types.FSInputFile(file_infographic), caption="📂 **Ваша инфографика:**\n\n_Эта схема построена программно на основе вашего текста._")
        
        await status_msg.delete()
        
        if os.path.exists(file_infographic): os.remove(file_infographic)

    except json.JSONDecodeError:
        logging.error(f"JSONDecodeError: ИИ вернул невалидный JSON: {ai_res}")
        await status_msg.edit_text("❌ ИИ вернул некорректный формат. Пожалуйста, попробуйте еще раз с другим текстом.")
    except Exception as e:
        logging.error(f"Error: {e}")
        await msg.answer("❌ Произошла ошибка обработки. Попробуйте отправить текст повторно.")

# --- ЗАПУСК ВЕБ-СЕРВЕРА И БОТА СИНХРОННО ---
async def main():
    port = int(os.getenv("PORT", 10000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    
    await asyncio.gather(
        server.serve(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
