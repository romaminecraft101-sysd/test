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
from google import genai

from fastapi import FastAPI
import uvicorn

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8916069792:AAHJYqH3NL42DpW4o-yA3vyN9B4gnuef8DI").strip()

# Список ключей Gemini
GEMINI_KEYS = [
    "AQ.Ab8RN6Lm1ouWvN0dozlZ2JMeQxzHYoRJfAKe8XdrG6NppLGd1Q",
    "AQ.Ab8RN6Lyunpjqo_qcbckjnHj0DErBBwbSsk0RHAvcg77Mgi1BQ",
    "AQ.Ab8RN6Lm1ePrmlKDffIqjRVuALOfPgPdzrhtmkjBS0diyEQudA"
]

# Актуальные названия моделей для SDK google-genai
MODELS_TO_TRY = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash']

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---
app = FastAPI()

@app.get("/")
@app.get("/health")
async def health():
    return {"status": "ok", "bot": "AI Infographic Generator"}

# --- ФУНКЦИЯ ДЛЯ БЕЗОПАСНОГО ВЫЗОВА GEMINI С РОТАЦИЕЙ КЛЮЧЕЙ И МОДЕЛЕЙ ---
async def generate_gemini_safe(prompt):
    for key in GEMINI_KEYS:
        # В новом SDK используется http_options вместо client_options
        client = genai.Client(api_key=key, http_options={'api_version': 'v1alpha'})
        for model_name in MODELS_TO_TRY:
            try:
                res = await client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={'response_mime_type': 'application/json'}
                )
                if res and res.text:
                    logging.info(f"✅ Успешный ответ от модели: {model_name}")
                    return res.text
            except Exception as e:
                logging.warning(f"Ошибка с моделью {model_name} (ключ ...{key[-5:]}): {e}. Пробуем дальше...")
                await asyncio.sleep(0.5)
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
    await msg.answer("🤖 **Привет! Я бот для создания инфографики.**\n\nПросто отправь мне любой текст (тему проекта, описание процесса, список идей), и я создам по нему схему-инфографику в формате PDF.")

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
    
    Верни ответ строго в формате JSON с одним ключом 'dot_code':
    {{
      "dot_code": "код_graphviz_здесь"
    }}
    """

    ai_res = await generate_gemini_safe(prompt)

    if not ai_res:
        await status_msg.edit_text("❌ Сервер ИИ временно перегружен или не смог обработать ваш запрос. Попробуйте еще раз через минуту.")
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
