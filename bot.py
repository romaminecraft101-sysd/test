import os
import io
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import BufferedInputFile

# Библиотеки для графики и PDF
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors

# Токен берется из переменных окружения (Environment Variables) на Render
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# --- 1. Генерация PNG изображения (Pillow) ---
def create_png_image(text_content: str) -> bytes:
    # Создаем холст 800x600 px (RGB, светлый фон)
    img = Image.new("RGB", (800, 600), color="#f0f0f0")
    draw = ImageDraw.Draw(img)

    # Рисуем рамку и круг
    draw.rectangle([50, 50, 750, 550], outline="#007acc", width=5)
    draw.ellipse([100, 100, 200, 200], fill="#ff4757")

    # Добавляем текст
    # Для стандартного шрифта можно использовать default, или закрузить свой .ttf файл
    font = ImageFont.load_default()
    draw.text((220, 140), text_content or "Привет из Python!", fill="#2f3542", font=font)

    # Сохраняем в байтовый поток (Buffer)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.getvalue()


# --- 2. Генерация PDF документа (ReportLab) ---
def create_pdf_document(text_content: str) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)

    # Заголовок
    pdf.setFont("Helvetica-Bold", 24)
    pdf.setFillColor(colors.HexColor("#007acc"))
    pdf.drawString(100, 700, "Generated PDF Document")

    # Прямоугольник
    pdf.setFillColor(colors.HexColor("#eccc68"))
    pdf.setStrokeColor(colors.HexColor("#ffa502"))
    pdf.rect(100, 450, 400, 200, fill=1, stroke=1)

    # Текст внутри
    pdf.setFillColor(colors.HexColor("#2f3542"))
    pdf.setFont("Helvetica", 14)
    pdf.drawString(120, 550, text_content or "Your text goes here")

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


# --- Хэндлеры бота ---
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer("Привет! Напиши /png для картинки или /pdf для документа.")


@dp.message(Command("png"))
async def png_handler(message: types.Message):
    png_bytes = create_png_image("Сгенерировано на Python!")
    photo = BufferedInputFile(png_bytes, filename="image.png")
    await message.answer_photo(photo, caption="Вот ваше PNG изображение")


@dp.message(Command("pdf"))
async def pdf_handler(message: types.Message):
    pdf_bytes = create_pdf_document("Документ создан без ошибок!")
    document = BufferedInputFile(pdf_bytes, filename="document.pdf")
    await message.answer_document(document, caption="Вот ваш PDF документ")


async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())