"""
Asosiy bot fayli
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# Handlerlarni import qilish
from handlers import basic, books, groups, admin, broadcast

# Konfiguratsiyani import qilish
import config

# Logging sozlamalari
logging.basicConfig(
    level=logging.DEBUG,  # DEBUG rejimini yoqish
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """Asosiy funksiya"""
    # Bot va dispatcher yaratish
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    
    # Handlerlarni ro'yxatga olish (tartib muhim!)
    # Buyruqlar birinchi bo'lishi kerak
    dp.include_router(basic.router)  # Buyruqlar (/start, /help) birinchi
    dp.include_router(admin.router)  # State filterli handlerlar avval
    dp.include_router(broadcast.router)  # Reklama tarqatish
    dp.include_router(books.router)  # Kitob qidirish
    dp.include_router(groups.router)  # Guruh xabarlari uchun (reklama bloklash) - oxirgi
    
    # Bot ma'lumotlarini tekshirish
    try:
        bot_info = await bot.get_me()
        logger.info(f"Bot ishga tushirildi: @{bot_info.username}")
        
        from aiogram.types import BotCommand
        global_commands = [
            BotCommand(command="start", description="Botni ishga tushirish"),
            BotCommand(command="help", description="Yordam olish"),
        ]
        
        await bot.set_my_commands(commands=global_commands)
        logger.info("Global komandalar sozlandi")
    except Exception as e:
        logger.error(f"Bot tokeni noto'g'ri: {e}")
        return
    
    # Konfiguratsiyani tekshirish
    if not config.ADMIN_ID:
        logger.warning("ADMIN_ID o'rnatilmagan!")
    
    if not config.STORAGE_CHANNEL_ID:
        logger.warning("STORAGE_CHANNEL_ID o'rnatilmagan!")
    
    # Adminni ogohlantirish: start
    if getattr(config, 'ADMIN_ID', None):
        try:
            await bot.send_message(config.ADMIN_ID, "✅ Bot ishga tushdi")
        except Exception as e:
            logger.warning(f"Adminni ogohlantirishda xatolik (start): {e}")

    try:
        # Botni ishga tushirish
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Bot ishga tushirishda xatolik: {e}")
    finally:
        # Adminni ogohlantirish: stop
        if getattr(config, 'ADMIN_ID', None):
            try:
                await bot.send_message(config.ADMIN_ID, "⛔️ Bot to'xtadi")
            except Exception as e:
                logger.warning(f"Adminni ogohlantirishda xatolik (stop): {e}")
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot to'xtatildi")
    except Exception as e:
        logger.error(f"Xatolik: {e}")
