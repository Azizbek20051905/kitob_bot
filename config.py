"""
Bot konfiguratsiyasi
"""
import os

# dotenv kutubxonasi mavjud bo'lsa ishlatish
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("dotenv kutubxonasi topilmadi, environment o'zgaruvchilaridan olinadi")

# Bot tokeni
BOT_TOKEN = os.getenv('BOT_TOKEN', 'your_bot_token_here')

# Admin ID
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))

# Saqlash kanali ID
STORAGE_CHANNEL_ID = os.getenv('STORAGE_CHANNEL_ID', '@your_storage_channel_id')

# Majburiy obuna kanallari (faqat admin tomonidan qo'shiladi)
REQUIRED_CHANNELS = []

# Ma'lumotlar bazasi fayli
DATABASE_PATH = 'database/bot.db'

# Ruxsat etilgan fayl turlari
ALLOWED_FILE_TYPES = {
    'pdf': 'document',
    'docx': 'document',
    'xlsx': 'document',
    'pptx': 'document',
    'mp3': 'audio',
    'wav': 'audio',
    'ogg': 'audio',
    'm4a': 'audio',
    'flac': 'audio'
}

# Maksimal fayl hajmi (MB)
MAX_FILE_SIZE = 700000
