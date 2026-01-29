import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from openai import AsyncOpenAI # Для DeepSeek
from google import genai
from google.genai import types as genai_types

# Инициализация DeepSeek
ds_client = AsyncOpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# Инициализация Gemini (для картинок)
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
dp = Dispatcher()

# --- Логика нейросетей ---

async def get_deepseek_response(text):
    try:
        response = await ds_client.chat.completions.create(
            model="deepseek-chat", # Или "deepseek-reasoner" для сложных задач
            messages=[
                {"role": "system", "content": "Ты крутой ИИ-ассистент в Телеграм."},
                {"role": "user", "content": text}
            ],
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ Ошибка DeepSeek: {str(e)}"

async def generate_banana_image(prompt):
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=f"High-quality digital art: {prompt}",
            config=genai_types.GenerateContentConfig(response_modalities=["IMAGE"])
        )
        return response.candidates[0].content.parts[0].inline_data.data
    except Exception as e:
        return str(e)

# --- Обработчики ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🤖 Бот на стероидах готов!\n\n"
                         "💬 **DeepSeek** отвечает на вопросы.\n"
                         "🎨 Команда **'Рисуй: [запрос]'** активирует Nano Banana.")

@dp.message(F.text.lower().startswith("рисуй:"))
async def handle_draw(message: types.Message):
    prompt = message.text[6:].strip()
    wait_msg = await message.answer("🍌 Nano Banana чистит кисточки...")
    
    result = await generate_banana_image(prompt)
    if isinstance(result, bytes):
        photo = types.BufferedInputFile(result, filename="art.png")
        await message.answer_photo(photo=photo, caption=f"Твой арт по запросу: {prompt}")
    else:
        await message.answer(f"❌ Ошибка генерации: {result}")
    await wait_msg.delete()

@dp.message()
async def handle_chat(message: types.Message):
    await bot.send_chat_action(message.chat.id, "typing")
    answer = await get_deepseek_response(message.text)
    await message.answer(answer)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
