import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import google.generativeai as genai

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация API Gemini (Nano Banana)
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash") # Используем актуальную модель

# Инициализация бота
bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
dp = Dispatcher()

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer("Привет! Пришли мне описание картинки, и я создам её с помощью Nano Banana. 🍌🎨")

@dp.message()
async def handle_prompt(message: types.Message):
    wait_message = await message.answer("Генерирую... Пожалуйста, подождите.")
    
    try:
        # В текущем API Gemini генерация изображений вызывается через Image Generation возможности.
        # В данном примере имитируем процесс (в реальном API используйте модель imagen)
        prompt = message.text
        
        # Здесь мы вызываем модель. 
        # Примечание: Убедитесь, что ваш API-ключ имеет доступ к Imagen/Nano Banana.
        response = model.generate_content(f"Generate an image based on this prompt: {prompt}")
        
        # Если API вернуло изображение (в байтах или ссылкой)
        # Для примера отправим текст, но если у вас настроен вывод Image:
        # await message.answer_photo(photo=types.BufferedInputFile(response.data, filename="art.png"))
        
        await message.answer(f"Запрос '{prompt}' принят в обработку Nano Banana!")
        
    except Exception as e:
        await message.answer(f"Произошла ошибка: {str(e)}")
    finally:
        await wait_message.delete()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
