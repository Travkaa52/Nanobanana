# bot_main.py
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from config.settings import TOKEN, ADMIN_ID
from database.db import connect, close
from handlers import *
from utils.logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

async def post_init(app):
    await connect()
    logger.info("✅ Бот запущен")

async def post_shutdown(app):
    await close()
    logger.info("👋 Бот остановлен")

def main():
    app = Application.builder()\
        .token(TOKEN)\
        .post_init(post_init)\
        .post_shutdown(post_shutdown)\
        .build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(catalog, pattern="^catalog$"))
    app.add_handler(CallbackQueryHandler(referral, pattern="^ref$"))
    app.add_handler(CallbackQueryHandler(withdraw, pattern="^withdraw$"))
    app.add_handler(CallbackQueryHandler(select_tariff, pattern="^tariff:"))
    app.add_handler(CallbackQueryHandler(handle_sex, pattern="^sex:"))
    app.add_handler(CallbackQueryHandler(skip_promo, pattern="^skip_promo$"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin$"))
    app.add_handler(CallbackQueryHandler(stats, pattern="^stats$"))
    app.add_handler(CallbackQueryHandler(approve_order, pattern="^approve:"))
    app.add_handler(CallbackQueryHandler(start, pattern="^home$"))
    
    # Сообщения
    app.add_handler(MessageHandler(filters.PHOTO, process_order))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_order))
    
    logger.info("🚀 Запуск...")
    app.run_polling()

if __name__ == "__main__":
    main()
