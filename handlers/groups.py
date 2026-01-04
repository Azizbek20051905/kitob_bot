"""
Guruh va kanal handlerlari - Reklama bloklash
"""
from aiogram import Router, F
from aiogram.types import Message
from database.db import Database
from utils.helpers import is_admin
import re
import config
import logging
import asyncio
from aiogram.filters import BaseFilter

logger = logging.getLogger(__name__)

router = Router()
db = Database()

async def is_group_admin(bot, chat_id: int, user_id: int) -> bool:
    """Guruh admini ekanligini tekshirish"""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except Exception as e:
        logger.error(f"Guruh admin tekshirishda xatolik: {e}")
        return False

async def can_bot_delete_messages(bot, chat_id: int) -> bool:
    """Botning guruhda xabarlarni o'chirish huquqi bor-yo'qligini tekshirish"""
    try:
        bot_member = await bot.get_chat_member(chat_id, bot.id)
        if bot_member.status == "creator":
            return True
        if bot_member.status == "administrator":
            return getattr(bot_member, 'can_delete_messages', False)
        return False
    except Exception as e:
        logger.error(f"Bot huquqlarini tekshirishda xatolik: {e}")
        return False

def count_emojis(text: str) -> int:
    """Matndagi emoji sonini hisoblash"""
    if not text:
        return 0
    # Emoji pattern (ko'p emoji turlarini qamrab oladi)
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"  # dingbats
        "\U000024C2-\U0001F251"  # enclosed characters
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA00-\U0001FA6F"  # chess symbols
        "\U0001FA70-\U0001FAFF"  # symbols and pictographs extended-A
        "\U00002600-\U000026FF"  # miscellaneous symbols
        "\U00002700-\U000027BF"  # dingbats
        "]+",
        flags=re.UNICODE
    )
    emojis = emoji_pattern.findall(text)
    return sum(len(e) for e in emojis)

def contains_advertisement(text: str) -> bool:
    """
    Mukammal reklama aniqlash funksiyasi (16 ta qoida asosida)
    
    Qoidalar:
    1. Ochiq linkli reklama (@kanal, t.me/...)
    2. Matn ichiga yashirilgan link
    3. So'z bilan yozilgan link (aldov)
    4. Emoji orqali yashirilgan reklama
    5. Rasm / Video caption
    6. Bio / imzo 
    7. "Oddiy gap" ko'rinishidagi reklama
    8. Savol shaklidagi reklama
    9. Kod, bo'shliq, belgilar bilan yashirish
    10. Takroriy spam reklama (generic checks)
    11. Faqat kanal nomi bilan reklama
    12. "Admin ruxsat berdi" aldovi
    13. Giveaway / konkurs
    14. Bot reklamalari
    15. Tashqi sayt reklamalari
    16. AI'ni aldashga qaratilgan semantik reklama
    """
    if not text:
        return False
    
    # 9. Kod, bo'shliq, belgilar bilan yashirish (Zero-width chars tozalash)
    # Zero-width space, joiner, non-joiner larni olib tashlaymiz
    clean_text = re.sub(r'[\u200b\u200c\u200d\u2060\ufeff]', '', text)
    # Ortiqcha bo'shliqlarni bittaga tushiramiz
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    text_lower = clean_text.lower()
    
    # 1. & 15. Ochiq linkli va Tashqi sayt reklamalari
    link_patterns = [
        r"https?://",
        r"t\.me/",
        r"telegram\.me/",
        r"\bt\.me\b",
        r"joinchat",
        r"\.(com|uz|ru|org|net|info|io|me|co|tk|ml|ga|cf|site|online|store|shop|xyz|click|link|club|live|life|world|space|tech|website|email)\b",
        r"bit\.ly", r"goo\.gl", r"tinyurl\.com", r"clck\.ru"
    ]
    if any(re.search(p, text_lower) for p in link_patterns):
        return True

    # Username aniqlash (@username)
    if re.search(r"@[a-zA-Z0-9_]{4,}", text_lower):
        return True

    # 3. So'z bilan yozilgan link (Obfuscated links)
    obfuscated_patterns = [
        r"t\s*me",               # t me
        r"telegram\s*me",        # telegram me
        r"t\s*\[\s*dot\s*\]\s*me", # t[dot]me
        r"telegram\s*nuqta\s*me",
        r"t\s*\.\s*me",
        r"dot\s*me",
        r"nuqta\s*me",
    ]
    if any(re.search(p, text_lower) for p in obfuscated_patterns):
        return True

    # 4. Emoji orqali yashirilgan reklama
    emoji_count = count_emojis(clean_text)
    text_len = len(clean_text.replace(' ', ''))
    
    # Faqat emojilardan iborat yoki juda ko'p emoji
    if text_len > 0 and (emoji_count / text_len > 0.4 or emoji_count > 8):
        # Agar ko'p emoji bo'lsa va tagida "kanal", "link" kabi so'zlar bo'lsa aniq spam
        if any(w in text_lower for w in ["kanal", "link", "kirish", "obuna", "pul", "click"]):
            return True

    # 5. Rasm / Video caption da @ yoki t.me (Main handler entitilar bilan tekshiradi, bu qo'shimcha)
    
    # 7. & 16. "Oddiy gap" va "Reklama emas" aldovi
    semantic_triggers = [
        r"reklama\s*emas",
        r"faqat\s*maslahat",
        r"tavsiya\s*qilaman",
        r"kanal\s*topdim",
        r"zo'?r\s*kanal",
        r"hamma\s*kiryapti",
        r"pul\s*ishlayapti",
        r"men\s*topdim",
        r"sinab\s*ko'?ring",
        r"o'?tib\s*oling",
        r"kirib\s*ko'?ring",
    ]
    if any(re.search(p, text_lower) for p in semantic_triggers):
        # Bu iboralar bo'lsa va qisqa matn bo'lsa (yoki link bo'lmasa ham) shubhali
        # Lekin "oddiy gap" bo'lishi mumkin, shuning uchun juda qat'iy emas,
        # agar bu iboralar bilan birga "kanal", "link" so'zi kelsa ushlaymiz
        if any(w in text_lower for w in ["kanal", "link", "guruh", "bot", "sayt"]):
            return True

    # 8. Savol shaklidagi reklama
    question_patterns = [
        r"pul\s*ishla(moqchi|shni)\s*misiz",
        r"kanal\s*bilasizmi",
        r"kimda\s*bor",
        r"qayerdan\s*topsa\s*bo'?ladi",
    ]
    if any(re.search(p, text_lower) for p in question_patterns):
        # Agar savol link yoki kanal haqida bo'lsa
        if "kanal" in text_lower or "bot" in text_lower or "link" in text_lower:
            return True

    # 11. Faqat kanal nomi (All caps yoki kanal nomi formati)
    # Masalan: ABC_KANAL
    if re.fullmatch(r"@[A-Z0-9_]+", clean_text) or re.fullmatch(r"[A-Z0-9_]{5,}_(CHANNEL|KANAL|TV|OFFICIAL)", clean_text):
        return True

    # 12. "Admin ruxsat berdi"
    if "admin" in text_lower and ("ruxsat" in text_lower or "kelishil" in text_lower):
        if "kanal" in text_lower or "reklama" in text_lower:
            return True

    # 13. Giveaway / konkurs
    giveaway_keywords = [
        "yutib ol", "sovrin", "konkurs", "giveaway", "obuna bo'ling", 
        "qatnashing", "shartlar", "g'olib"
    ]
    if any(k in text_lower for k in giveaway_keywords) and ("kanal" in text_lower or "obuna" in text_lower):
        return True

    # 14. Bot reklamalari
    if "bot" in text_lower and ("start" in text_lower or "foydalan" in text_lower or "kiring" in text_lower):
         return True
    
    # Bot username aniqlash (bot bilan tugagan)
    if re.search(r"@[a-zA-Z0-9_]+bot\b", text_lower):
        return True

    # 10. Takroriy spam - buni aniqlash qiyin (chunki state yo'q), lekin 
    # umumiy reklama iboralarini tekshiramiz
    general_spam_keywords = [
        "reklama", "sotiladi", "aksiya", "chegirma", "arzon", "sifatli",
        "dostavka", "yetkazib berish", "xizmati", "click here", "buy now",
        "limited offer", "exclusive", "crypto", "bitcoin", "invest",
        "daromad", "biznes", "online ish", "uydan ish"
    ]
    if any(k in text_lower for k in general_spam_keywords):
        return True
    
    # 9. Kod, bo'shliqlar bilan ajratilgan (t . m e / a b c)
    # Harflar orasida bo'shliq borligini tekshirish
    spaced_text = re.sub(r'\s+', '', text_lower)
    if "t.me/" in spaced_text or "telegram.me" in spaced_text:
        return True

    return False

class SpamFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        # 1. Bot xabarlari va botlar e'tiborsiz qoldiriladi
        if not message.from_user or message.from_user.is_bot:
            return False
            
        # 2. Bot adminlari (config.ADMIN_ID) e'tiborsiz qoldiriladi (reklama tashlay oladi)
        if is_admin(message.from_user.id):
            return False
            
        # 3. Guruh adminlari ham e'tiborsiz qoldiriladi
        if await is_group_admin(message.bot, message.chat.id, message.from_user.id):
            return False
            
        # 4. Botning o'chirish huquqini tekshirish (agar o'chira olmasa, baribir spam deb topmaymiz,
        # chunki foydasi yo'q va log to'lib ketadi)
        if not await can_bot_delete_messages(message.bot, message.chat.id):
            return False
            
        # 5. Forward qilingan kanal postlari - bu SPAM
        if getattr(message, 'forward_from_chat', None) and getattr(message.forward_from_chat, 'type', None) == 'channel':
            return True
            
        # 6. Matn tarkibini tekshirish
        text_to_check = message.text or message.caption or ""
        
        # Buyruqlar (/start) spam emas (admin tekshiruvidan o'tmagan memberlar uchun ham)
        if text_to_check.startswith("/"):
            return False
            
        if contains_advertisement(text_to_check):
            return True
            
        # 7. Entities (yashirin linklar)
        if message.entities:
            for ent in message.entities:
                if ent.type in ["url", "text_link", "mention", "email"]:
                    return True
        
        if message.caption_entities:
            for ent in message.caption_entities:
                if ent.type in ["url", "text_link", "mention", "email"]:
                    return True
                    
        return False

@router.message(F.chat.type.in_(["group", "supergroup"]), SpamFilter(), flags={"block": False})
async def anti_advertisement_guard(message: Message):
    """
    Faqat SpamFilter True qaytarganida ishlaydi (ya'ni reklama aniqlanganda).
    Reklama xabarlarini o'chiradi va ogohlantiradi.
    """
    try:
        # Xabarni o'chirish
        await message.delete()
        
        # Ogohlantirish (foydalanuvchini belgilab)
        # Xabar o'chirilmaydi (user talabi)
        user_mention = f"[{message.from_user.full_name}](tg://user?id={message.from_user.id})"
        await message.answer(
            f"⚠️ {user_mention}, guruhda reklama yoki havola tashlash taqiqlangan!",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Spamni tozalashda xatolik: {e}")


