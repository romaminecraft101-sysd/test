import os
import io
import json
import asyncio
import textwrap
from aiohttp import web

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import BufferedInputFile

from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI

# Redder irraa geeddaramtoota naannoo (Environment Variables) fudhachuu
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# OpenRouter client qopheessuu
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
) if OPENROUTER_API_KEY else None

# Jechoota Qubee Sirriitti Mul'isuuf (Font)
FONT_PATH = "Roboto-Regular.ttf"

def get_font(size: int):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()

# --- Ajaja Ajajamu (System Prompt) ---
SYSTEM_PROMPT = """
You are a UI/UX designer. Output ONLY valid JSON (without markdown ```json wrappers) for an image config (1000x800 px).

JSON structure:
{
  "bg_color": "#HEX",
  "shapes": [
    {"type": "rectangle" | "circle" | "line", "coords": [x1, y1, x2, y2], "color": "#HEX", "width": 2}
  ],
  "texts": [
    {"text": "Text in Russian", "x": 100, "y": 100, "color": "#HEX", "size": 24, "max_width": 30}
  ]
}
"""

# --- PNG Fakkii Uumuu ---
def draw_image_from_config(config: dict) -> bytes:
    img = Image.new("RGB", (1000, 800), color=config.get("bg_color", "#0b0d17"))
    draw = ImageDraw.Draw(img)

    # 1. Bifa (Shapes) fakkessuu
    for shape in config.get("shapes", []):
        stype = shape.get("type")
        coords = shape.get("coords", [0, 0, 100, 100])
        color = shape.get("color", "#ffffff")
        width = shape.get("width", 2)

        if stype == "rectangle":
            draw.rectangle(coords, fill=color)
        elif stype == "circle":
            draw.ellipse(coords, fill=color)
        elif stype == "line":
            draw.line(coords, fill=color, width=width)

    # 2. Barruu (Text) barreessuu
    for text_info in config.get("texts", []):
        raw_text = text_info.get("text", "")
        x = text_info.get("x", 50)
        y = text_info.get("y", 50)
        color = text_info.get("color", "#ffffff")
        size = text_info.get("size", 20)
        max_width = text_info.get("max_width", 35)

        font = get_font(size)
        wrapped_lines = textwrap.wrap(raw_text, width=max_width)
        
        current_y = y
        for line in wrapped_lines:
            draw.text((x, current_y), line, fill=color, font=font)
            current_y += size + 4

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.getvalue()


# --- Ergaa Telegram ---
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer(
        "Akkam! Mata duree fakkii maaliitu siif uumamu barbaadda?\n\n"
        "Fakkeenyaaf: *'Черная дыра'* ykn *'Кофейня'*"
    )

@dp.message(F.text)
async def generate_custom_image(message: types.Message):
    if not client:
        await message.answer("❌ Owwaannaa: OPENROUTER_API_KEY Render irratti hin saagalle!")
        return

    user_prompt = message.text
    status_msg = await message.answer("📊 OpenRouter AI fayyadamnee fakkii qopheessaa jirra...")

    # Tarree modelliwwan bilisaa (Free models)
    FREE_MODELS = [
        "google/gemini-2.0-flash-exp:free",
        "google/gemini-flash-1.5-8b:free",
        "meta-llama/llama-3.1-8b-instruct:free",
        "qwen/qwen-2.5-7b-instruct:free",
        "mistralai/mistral-7b-instruct:free"
    ]

    response = None
    last_error = ""

    # Tokko tokkoon yaaluu
    for model_name in FREE_MODELS:
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ]
            )
            if response and response.choices:
                print(f"Modelliin hojjete: {model_name}")
                break
        except Exception as e:
            last_error = str(e)
            print(f"Model {model_name} hin hojjenne, isa itti aanutti darbina...")
            await asyncio.sleep(1)
            continue

    if not response or not response.choices:
        await status_msg.edit_text(f"❌ Dogoggora: Modelliin bilisaa tajaajila ala ta'aniiru. {last_error[:150]}")
        return

    try:
        raw_content = response.choices[0].message.content
        raw_json = raw_content.replace("```json", "").replace("```", "").strip()
        config = json.loads(raw_json)

        png_bytes = draw_image_from_config(config)
        photo = BufferedInputFile(png_bytes, filename="infographic.png")

        await status_msg.delete()
        await message.answer_photo(photo, caption=f"Fakkii uumame: *{user_prompt}*")

    except Exception as e:
        await status_msg.edit_text(f"❌ Dogoggora JSON: {str(e)}")


# --- Server Render.com Webhook/Ping ---
async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def main():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    print(f"Serveriin portii {port} irratti ka'eera...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
