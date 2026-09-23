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

from huggingface_hub import InferenceClient

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8916069792:AAHJYqH3NL42DpW4o-yA3vyN9B4gnuef8DI").strip()

# Твой API токен Hugging Face (получить на huggingface.co -> Settings -> Access Tokens)
HF_TOKEN = os.getenv("HF_TOKEN", "hf_ТВОЙ_КЛЮЧ_ЗДЕСЬ").strip()

# Модель Qwen 2.5 Coder отлично подходит для генерации разметки Graphviz и JSON
# Примечание: Для использования этой модели может потребоваться согласие с условиями на странице модели на HF.
HF_MODEL_NAME = "Qwen/Qwen2.5-Coder-32B-Instruct" 

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()

# Инициализация клиента Hugging Face
# Если HF_TOKEN не задан или некорректен, InferenceClient будет работать без авторизации (с ограничениями)
hf_client = InferenceClient(model=HF_MODEL_NAME, token=HF_TOKEN if HF_TOKEN.startswith("hf_") else None)

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---
app = FastAPI()

@app.get("/")
@app.get("/health")
async def health():
    return {"status": "ok", "bot": "AI Infographic Generator (HuggingFace)"}

# --- ФУНКЦИЯ ВЫЗОВА HUGGING FACE ---
async def generate_hf_safe(prompt):
    messages = [
        {"role": "system", "content": "You are a helpful assistant that strictly responds in JSON format."},
        {"role": "user", "content": prompt}
    ]
    try:
        # Запускаем синхронный запрос к HuggingFace в асинхронном потоке
        # asyncio.to_thread позволяет выполнять синхронные функции без блокировки основного цикла
        response = await asyncio.to_thread(
            hf_client.chat_completion,
            messages=messages,
            max_tokens=1000, # Максимальное количество токенов в ответе
            temperature=0.2, # Низкий temperature для более детерминированных ответов (код/JSON)
            do_sample=True,  # Включено для использования temperature
            return_full_text=False # Возвращает только сгенерированный текст, без промпта
        )
        
        content = response.choices[0].message.content.strip()
        
        # Очистка от возможных markdown-тегов ```json ... ```
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:] # Удаляем первую строку (```json)
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1] # Удаляем последнюю строку (```)
            content = "\n".join(lines).strip()
            
        return content
    except Exception as e:
        logging.error(f"Ошибка вызова Hugging Face API с моделью {HF_MODEL_NAME}: {e}")
        return None

# --- ГЕНЕРАЦИЯ PDF-СХЕМЫ ЧЕРЕЗ QuickChart ---
def get_quickchart_pdf(dot_code, user_id):
    clean_code = dot_code.replace("```dot", "").replace("```", "").strip()
    encoded_code = urllib.parse.quote(clean_code)
    url = f"https://quickchart.io/graphviz?format=pdf&graph={encoded_code}"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status() # Вызовет исключение для ошибок HTTP (4xx или 5xx)
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

    # Промпт для Hugging Face: Сгенерировать Graphviz (DOT) код на основе произвольного текста
    # Строго просим вернуть JSON.
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
        await status_msg.edit_text("❌ ИИ-сервер временно не отвечает или не смог обработать ваш запрос. Попробуйте еще раз через минуту.")
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
