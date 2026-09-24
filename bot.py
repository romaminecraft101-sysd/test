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
# Подтягиваем переменные из настроек Render
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

# Модель DeepSeek через OpenRouter (очень быстрая и дешевая)
OPENROUTER_MODEL = "deepseek/deepseek-chat"

logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER (чтобы не засыпал) ---
app = FastAPI()

@app.get("/")
@app.get("/health")
async def health():
    return {"status": "ok", "bot": "AI Infographic Generator (OpenRouter)"}

# --- ФУНКЦИЯ ВЫЗОВА OPENROUTER ---
async def generate_openrouter_safe(prompt):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that strictly responds in JSON format."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 1000
    }

    def send_request():
        # Отправляем запрос на OpenRouter
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions", 
            headers=headers, 
            json=payload, 
            timeout=60
        )
        return response

    try:
        response = await asyncio.to_thread(send_request)
        
        if response.status_code != 200:
            logging.error(f"OpenRouter API Error [{response.status_code}]: {response.text}")
            return None

        res_json = response.json()
        content = res_json["choices"][0]["message"]["content"].strip()

        # Очистка от markdown-тегов ```json ... ``` если ИИ их добавил
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()
            
        return content
    except Exception as e:
        logging.error(f"Ошибка вызова OpenRouter API: {e}")
        return None

# --- ГЕНЕРАЦИЯ PDF-СХЕМЫ ЧЕРЕЗ QuickChart (Graphviz) ---
def get_quickchart_pdf(dot_code, user_id):
    # Кодируем DOT-код для URL
    clean_code = dot_code.replace("```dot", "").replace("```", "").strip()
    encoded_code = urllib.parse.quote(clean_code)
    url = f"https://quickchart.io/graphviz?format=pdf&graph={encoded_code}"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при запросе к QuickChart: {e}")
        return None

    # Сохраняем временный файл
    filename = f"infographic_{user_id}.pdf"
    with open(filename, "wb") as f:
        f.write(response.content)
    return filename

# --- ОБРАБОТЧИКИ (ХЕНДЛЕРЫ) ---

@dp.message(Command("start"))
async def cmd_start(msg: types.Message):
    await msg.answer("🤖 **Привет! Я бот для создания инфографики.**\n\nОтправь мне любую тему или текст, и я превращу это в логическую PDF-схему!")

@dp.message(F.text)
async def handle_user_text(msg: types.Message):
    user_text = msg.text
    status_msg = await msg.answer("⏳ **ИИ анализирует текст и рисует схему...**")

    # Промпт для генерации Graphviz кода
    prompt = f"""На основе следующего текста создай логическую схему (инфографику) в формате Graphviz (DOT):
    ---
    {user_text}
    ---
    Правила:
    1. Направление сверху вниз (rankdir=TB).
    2. Узлы формы 'box' со скругленными углами.
    3. Цвета: фон белый, узлы светло-голубые (lightblue).
    4. 5-7 ключевых этапов.
    5. Текст внутри блоков на РУССКОМ языке.
    
    Верни ответ СТРОГО в формате JSON:
    {{
      "dot_code": "код_graphviz_здесь"
    }}
    """

    # 1. Получаем код от ИИ
    ai_res = await generate_openrouter_safe(prompt)

    if not ai_res:
        await status_msg.edit_text("❌ Ошибка ИИ. Попробуй еще раз через минуту.")
        return

    try:
        res_data = json.loads(ai_res)
        dot_code = res_data.get('dot_code')

        if not dot_code:
            await status_msg.edit_text("❌ ИИ не смог составить схему. Попробуй другой текст.")
            return

        # 2. Генерируем PDF через QuickChart
        file_infographic = get_quickchart_pdf(dot_code, msg.from_user.id)

        if not file_infographic:
            await status_msg.edit_text("❌ Ошибка отрисовки PDF.")
            return

        # 3. Отправляем готовый файл
        await bot.send_document(
            msg.chat.id, 
            types.FSInputFile(file_infographic), 
            caption="📂 **Ваша инфографика готова!**"
        )
        
        await status_msg.delete()
        
        # Удаляем временный файл с сервера
        if os.path.exists(file_infographic):
            os.remove(file_infographic)

    except json.JSONDecodeError:
        await status_msg.edit_text("❌ ИИ прислал неверный формат данных.")
    except Exception as e:
        logging.error(f"Error: {e}")
        await msg.answer("❌ Произошла ошибка.")

# --- ЗАПУСК ---
async def main():
    # Настройка порта для Render
    port = int(os.getenv("PORT", 10000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    
    # Запускаем сервер и бота одновременно
    await asyncio.gather(
        server.serve(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
