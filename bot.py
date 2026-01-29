import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from google import genai
from google.genai import types as genai_types
from io import BytesIO

# Инициализация клиента (новый SDK 2026 года)
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Инициализация бота
bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
dp = Dispatcher()

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer("Бот Nano Banana 🍌 готов к работе! Пришли описание, и я создам арт.")

@dp.message()
async def handle_prompt(message: types.Message):
    wait_msg = await message.answer("🎨 Рисую... Это займет около 10 секунд.")
    
    try:
        # Вызов Nano Banana (Gemini 2.5 Flash Image)
        response = client.models.generate_content(
            model="gemini-2.5-flash-image", # Актуальная модель для генерации
            contents=message.text,
            config=genai_types.GenerateContentConfig(
                response_modalities=["IMAGE"] # Явно указываем, что ждем картинку
            )
        )

        # Извлекаем изображение из ответа
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                photo_bytes = part.inline_data.data
                photo = types.BufferedInputFile(photo_bytes, filename="banana_art.png")
                await message.answer_photo(photo=photo, caption=f"Вот твой запрос: {message.text}")
                break
        else:
            await message.answer("Хм, модель не вернула изображение. Попробуй другой промпт.")

    except Exception as e:
        await message.answer(f"❌ Ошибка API: {str(e)}")
    finally:
        await wait_msg.delete()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
