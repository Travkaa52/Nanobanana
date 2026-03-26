# bot_main.py
import os
import logging
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, 
    filters
)

# Загружаем переменные окружения
load_dotenv()

# Импортируем наши хендлеры и функции
from handlers import (
    start, about_handler, feedback_handler, ref_menu, withdraw_handler,
    show_catalog, select_tariff, handle_message, select_sex,
    handle_promocode_input, skip_promo_handler, handle_media,
    handle_admin_reply, admin_reply_feedback, admin_approve,
    admin_confirm_withdraw, admin_panel_command, admin_panel,
    admin_stats, admin_tariffs_menu, admin_promocodes_menu,
    admin_promo_add_start, admin_broadcast_menu, admin_users_list,
    admin_feedback_list, handle_broadcast_message, execute_broadcast,
    handle_new_promo_input, handle_new_tariff_input, admin_tariff_toggle,
    admin_tariff_edit_price, admin_tariff_edit_name, admin_tariff_add_start,
    error_handler, button_handler, tariff_info_handler
)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO"))
)
logger = logging.getLogger(__name__)

async def post_init(application: Application):
    """Функция, которая выполняется после инициализации приложения"""
    from db import init_db_pool
    await init_db_pool()
    logger.info("✅ База данных PostgreSQL инициализирована")
    print("✅ База данных подключена")

async def post_shutdown(application: Application):
    """Функция, которая выполняется перед остановкой бота"""
    from db import close_db_pool
    await close_db_pool()
    logger.info("✅ Соединение с базой данных закрыто")
    print("✅ Соединение с базой данных закрыто")

def main():
    """Запуск бота"""
    try:
        # Получаем токен
        TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TOKEN")
        if not TOKEN:
            raise ValueError("❌ Токен бота не знайдено в змінних оточення!")
        
        # Создаем приложение
        app = Application.builder().token(TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()
        
        # Добавляем обработчики команд
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", start))
        app.add_handler(CommandHandler("admin", admin_panel_command))
        
        # Добавляем обработчики callback-запросов
        app.add_handler(CallbackQueryHandler(button_handler))
        
        # Добавляем обработчики сообщений
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_media))
        
        # Добавляем обработчик ошибок
        app.add_error_handler(error_handler)
        
        logger.info("🌸 Бот FunsDiia готов к запуску!")
        print("✅ Бот готов к запуску!")
        print(f"👑 Адмін-панель: /admin")
        print("🐘 База данных: PostgreSQL Aiven")
        print("🚀 Запуск бота...")
        
        # Запускаем бота (он сам управляет event loop)
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Критична помилка при запуску: {e}")
        print(f"❌ Критична помилка: {e}")
        raise

if __name__ == "__main__":
    main()