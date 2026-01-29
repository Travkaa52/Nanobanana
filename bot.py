import os, asyncio, logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from google import genai
from google.genai import types as genai_types

# Настройка
logging.basicConfig(level=logging.INFO)
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
dp = Dispatcher()
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

# Хранилище пользователей (в памяти, пока бот запущен)
users_db = set()

# --- Вспомогательные функции ---

async def call_ai(prompt, image_bytes=None, audio_bytes=None):
    model = "gemini-2.0-flash-exp"
    contents = [prompt] if prompt else ["Опиши это"]
    
    if image_bytes:
        contents.append(genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))
    if audio_bytes:
        contents.append(genai_types.Part.from_bytes(data=audio_bytes, mime_type="audio/ogg"))
        contents[0] = "Транскрибируй это голосовое сообщение на русском языке."

    try:
        response = client.models.generate_content(model=model, contents=contents)
        return response.text
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

# --- Админ-панель ---

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("🔒 Доступ закрыт.")
    
    kb = [
        [types.InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [types.InlineKeyboardButton(text="📢 Рассылка", callback_data="broadcast")]
    ]
    await message.answer("🛠 Панель управления ботом:", 
                         reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "stats")
async def show_stats(callback: types.CallbackQuery):
    await callback.message.edit_text(f"📈 Пользователей в базе: {len(users_db)}")

# --- Основные функции ---

@dp.message(Command("start"))
async def start(message: types.Message):
    users_db.add(message.from_user.id)
    await message.answer("🤖 Я твой ИИ-комбайн!\n\n"
                         "🎙 Шли голосовые — я пойму.\n"
                         "🖼 Шли фото — я увижу.\n"
                         "🎨 Пиши /draw — я нарисую.")

@dp.message(Command("draw"))
async def draw(message: types.Message):
    prompt = message.text.replace("/draw", "").strip()
    if not prompt: return await message.answer("Что рисуем?")
    
    msg = await message.answer("⌛️ Генерирую...")
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp", # Для Nano Banana
            contents=prompt,
            config=genai_types.GenerateContentConfig(response_modalities=["IMAGE"])
        )
        photo = types.BufferedInputFile(response.candidates[0].content.parts[0].inline_data.data, filename="art.png")
        await message.answer_photo(photo=photo)
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
    await msg.delete()

@dp.message(F.voice)
async def handle_voice(message: types.Message):
    await bot.send_chat_action(message.chat.id, "typing")
    file = await bot.get_file(message.voice.file_id)
    audio = await bot.download_file(file.file_path)
    text = await call_ai(None, audio_bytes=audio.read())
    await message.reply(f"🎤 **Распознано:**\n{text}")

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    await bot.send_chat_action(message.chat.id, "typing")
    file = await bot.get_file(message.photo[-1].file_id)
    img = await bot.download_file(file.file_path)
    text = await call_ai(message.caption, image_bytes=img.read())
    await message.reply(text)

@dp.message()
async def chat(message: types.Message):
    users_db.add(message.from_user.id)
    await bot.send_chat_action(message.chat.id, "typing")
    ans = await call_ai(message.text)
    await message.answer(ans)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
