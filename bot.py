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
from playwright.async_api import async_playwright

# --- НАСТРОЙКИ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = "deepseek/deepseek-chat"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()
app = FastAPI()

# Хранилище настроек формата пользователей
user_formats = {}

@app.get("/health")
async def health():
    return {"status": "ok"}

async def generate_infographic_html(topic: str) -> str:
    """Генерирует насыщенную техническую HTML/CSS верстку инфографики уровня Gemini Notebook / NotebookLM."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    system_prompt = (
        "Вы — ведущий инженер по технической иллюстрации и HTML/CSS верстке, работающий в стиле Gemini Notebook / NotebookLM.\n\n"
        "ТРЕБОВАНИЯ К ГЕНЕРИРУЕМОЙ HTML-ИНФОГРАФИКЕ:\n"
        "1. ЯЗЫК: Строго РУССКИЙ.\n"
        "2. ВИЗУАЛЬНЫЙ СТИЛЬ (Gemini Notebook Style):\n"
        "   - Светлый инженерный фон (#F8FAFC) с четкими темно-синими рамками (#1E293B) и закругленными карточками (12px).\n"
        "   - Четкая строгая типографика (Inter/Roboto/Arial), крупный выразительный заголовок вверху с подзаголовком.\n"
        "   - Высокая плотность информации: используйте схемы с шагами, цепочки процессов, стрелочки между блоками, векторную паутинную диаграмму (Radar Chart) и таблицы.\n"
        "3. ОБЯЗАТЕЛЬНЫЕ ЭЛЕМЕНТЫ:\n"
        "   - Главный заголовок и подзаголовок вверху страницы.\n"
        "   - Внешние контурные блоки-группы с вшитым в верхнюю рамку заголовком секции (например, 'АРХИТЕКТУРА ИСПОЛНЕНИЯ И СРЕДЫ').\n"
        "   - Пошаговые диаграммы процессов (Flowcharts) с векторными стрелочками (→) между этапами (Исходный код → Компилятор → Байт-код → Процессор).\n"
        "   - Встроенные инлайн SVG-иконки для ключевых элементов (процессор, документы, код, аватар разработчика, сборщик мусора, шестеренки, паутинная диаграмма).\n"
        "   - Сравнительная структурированная таблица внизу с темной шапкой и четкими границами ячеек.\n"
        "4. ВАЖНО: Не генерируйте пустые или минималистичные блоки! Делайте полноценную, глубокую, технически детализированную инфографику со схемами, иконками и подробными пояснениями внутри каждого блока.\n"
        "5. Выдавайте ТОЛЬКО готовый валидный HTML-код (с CSS внутри <style>) в блоке ```html ... ``` без лишних комментариев и оберток."
    )

    user_prompt = f"Создай подробную техническую инфографику в стиле Gemini Notebook на тему: '{topic}'."

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 4000
    }

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            res = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
            if res.status_code == 200:
                content = res.json()["choices"][0]["message"]["content"].strip()
                if "```html" in content:
                    content = content.split("```html")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                return content
            else:
                logging.error(f"OpenRouter status {res.status_code}: {res.text}")
    except Exception as e:
        logging.error(f"HTML generation error: {e}")
    
    return None

async def render_html_to_png(html_content: str, width: int = 1200, height: int = 1600) -> bytes:
    """Рендерит HTML-верстку в 4K PNG скриншот через headless браузер Chromium."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        # device_scale_factor=2 дает четкость Retina/4K
        context = await browser.new_context(
            viewport={'width': width, 'height': height},
            device_scale_factor=2
        )
        page = await context.new_page()
        
        # Загружаем HTML в виртуальный браузер
        await page.set_content(html_content, wait_until="networkidle")
        
        # Делаем скриншот всей страницы
        screenshot_bytes = await page.screenshot(type="png", full_page=True)
        await browser.close()
        return screenshot_bytes

@dp.message(Command("start"))
async def cmd_start(msg: types.Message):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="3:4 (Вертикальный плакат)", callback_data="format_1200_1600")],
        [types.InlineKeyboardButton(text="16:9 (Горизонтальный)", callback_data="format_1600_900")],
        [types.InlineKeyboardButton(text="1:1 (Квадрат)", callback_data="format_1200_1200")]
    ])
    await msg.answer("🎨 **Выберите формат инфографики (Gemini Notebook):**", reply_markup=kb)

@dp.callback_query(F.data.startswith("format_"))
async def set_format_callback(callback: types.CallbackQuery):
    parts = callback.data.split('_')
    width_str, height_str = parts[1], parts[2]
    
    user_id = callback.from_user.id
    user_formats[user_id] = {"width": int(width_str), "height": int(height_str)}
    
    await callback.message.edit_text(
        f"✅ Формат установлен: **{width_str}x{height_str}**.\nОтправьте тему для создания инфографики.",
        reply_markup=None
    )
    await callback.answer("Формат сохранен.", show_alert=False)

@dp.message(F.text)
async def handle_text(msg: types.Message):
    user_id = msg.from_user.id
    current_format = user_formats.get(user_id, {"width": 1200, "height": 1600})

    status_msg = await msg.answer("📊 **Проектирую схемы и структуру (Gemini Notebook)...**")

    # 1. Генерируем HTML-код с помощью DeepSeek
    html_code = await generate_infographic_html(msg.text)
    
    if not html_code:
        await status_msg.edit_text("❌ Ошибка при формировании структуры. Попробуйте еще раз.")
        return

    await status_msg.edit_text("📸 **Рендерю векторную инфографику в UltraHD...**")

    # 2. Рендерим HTML в PNG с помощью Playwright
    try:
        image_bytes = await render_html_to_png(
            html_content=html_code, 
            width=current_format["width"], 
            height=current_format["height"]
        )

        document_file = BufferedInputFile(image_bytes, filename="notebook_infographic.png")

        await bot.send_document(
            msg.chat.id, 
            document=document_file, 
            caption=f"✅ **Ваша инфографика:** {msg.text[:50]}..."
        )
        await status_msg.delete()
    except Exception as e:
        logging.error(f"Render error: {e}")
        await status_msg.edit_text("❌ Ошибка при рендеринге изображения.")

async def main():
    port = int(os.getenv("PORT", 10000))
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port))
    await asyncio.gather(server.serve(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())
