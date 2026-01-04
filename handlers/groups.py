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
    """Reklama aniqlash funksiyasi - emoji spam va linklarni ham tekshiradi"""
    if not text:
        return False
    
    text_lower = text.lower()
    
    # 1. Emoji spam tekshirish - agar emoji soni juda ko'p bo'lsa
    emoji_count = count_emojis(text)
    text_length = len(text.replace(' ', '').replace('\n', ''))
    if text_length > 0:
        emoji_ratio = emoji_count / text_length
        # Agar emoji 30% dan ko'p bo'lsa yoki 10+ emoji bo'lsa
        if emoji_ratio > 0.3 or emoji_count >= 10:
            logger.debug(f"Emoji spam aniqlandi: {emoji_count} emoji, ratio: {emoji_ratio:.2f}")
            return True
    
    # 2. Link patternlari (yaxshilangan)
    link_patterns = [
        r"https?://",                 # http/https linklar
        r"\bt\.me/",                  # t.me linklari (barcha turdagi)
        r"\bt\.me/[a-zA-Z0-9_]+",     # Telegram kanal/bot havolalari (@ kanallar ham)
        r"\bt\.me/c/\d+/\d+",         # private post linklari
        r"t\.me/m/[A-Za-z0-9]+",      # t.me/m/ formatidagi linklar
        r"joinchat/",                 # eski joinchat linklari
        r"t\.me/\+[a-zA-Z0-9_-]{10,}", # t.me/+XXXX invite (to'liq format)
        r"\+[a-zA-Z0-9_-]{10,}",      # t.me/+XXXX invite (qisqa format)
        r"bit\.ly/[a-zA-Z0-9]+",      # Qisqartirilgan havolalar (bit.ly)
        r"clck\.ru/[a-zA-Z0-9]+",     # Qisqartirilgan havolalar (clck.ru)
        r"tinyurl\.com/[a-zA-Z0-9]+", # Qisqartirilgan havolalar (tinyurl)
        r"short\.link/[a-zA-Z0-9]+",  # Qisqartirilgan havolalar
        r"utm_source=",               # UTM parametrlari (tracking links)
        r"utm_campaign=",             # UTM parametrlari
        r"utm_medium=",               # UTM parametrlari
        r"\.(com|uz|ru|org|net|info|io|me|co|tk|ml|ga|cf|site|online|store|shop|xyz|click|link)\b",  # domenlar (kengaytirilgan)
    ]
    
    if any(re.search(p, text_lower) for p in link_patterns):
        return True
    
    # 3. @username mentionlar va Telegram havolalari
    if re.search(r"@[a-zA-Z0-9_]{5,}", text):
        return True
    
    # Telegram inline havolalar (kanal/bot nomlari bilan)
    if re.search(r"t\.me/@?[a-zA-Z0-9_]{3,}", text_lower):
        return True
    
    # 4. Telefon raqamlari va boshqa reklama belgilari
    spam_patterns = [
        r"\b\d{2,3}[-\s]??\d{2,3}[-\s]??\d{2}[-\s]?\d{2}\b",  # telefon raqamlari
        r"\b\d{7,}\b",              # uzun raqamlar
        r"\b\d+%\b",                 # foiz
        r"[₩¥$€£]",                  # valyuta belgilar
    ]
    
    if any(re.search(p, text_lower) for p in spam_patterns):
        return True
    
    # 5. Reklama kalit so'zlari (kengaytirilgan ro'yxat)
    
    # O'zbekcha reklama so'zlari
    uzbek_keywords = [
        "reklama", "aksiya", "chegirma", "arzon", "sotuv", "bonus",
        "kurs", "dars", "jonli dars", "videodars", "kanalimizda",
        "murojaat uchun", "bog'lanish uchun", "obuna", "promo",
        "qo'shiling", "obuna bo'ling", "kanalga", "guruhga",
        "tez kiring", "shoshiling", "bepul", "qanday", "sirlari",
        "sotiq", "narxlar", "top-10", "top 10", "faqat bugun",
        "oxirgi imkoniyat", "pul ishlash", "biznes", "ta'lim",
        "batafsil", "ko'rish", "yangi", "investitsiya",
        "bosish", "a'zo bo'lish", "o'tish", "bog'lanish", "olish",
        "buyurtma berish", "chegirmalar", "maxsus taklif"
    ]
    
    # Inglizcha reklama so'zlari
    english_keywords = [
        "click here", "learn more", "free", "discount", "limited time",
        "hurry", "don't miss out", "secret", "must-see", "top 10",
        "new", "guaranteed", "invest", "subscribe", "join", "unlock",
        "save", "subscribe", "join our channel", "limited offer",
        "special offer", "act now", "buy now", "order now",
        "get started", "sign up", "register now", "claim now"
    ]
    
    # Ruscha reklama so'zlari
    russian_keywords = [
        "перейти", "подробнее", "смотреть", "скидка", "бесплатно",
        "спешите", "акция", "только сегодня", "как", "секреты",
        "топ", "заработок", "бизнес", "обучение", "инвестиции",
        "подпишись", "подпишитесь", "реклама", "акция", "распродажа",
        "кликни", "нажми", "переходи", "смотри", "узнай",
        "получи", "заказать", "купить", "оформить"
    ]
    
    # Barcha kalit so'zlarni birlashtirish
    all_keywords = uzbek_keywords + english_keywords + russian_keywords
    
    if any(k in text_lower for k in all_keywords):
        return True
    
    # 6. CTA (Call to Action) iboralarini tekshirish
    cta_patterns = [
        r"\b(bosish|bos|bosing)\b",  # Bosish
        r"\b(a'zo bo'lish|a'zo bo'ling|obuna bo'ling)\b",  # A'zo bo'lish
        r"\b(o'tish|o'ting|kirish|kiring)\b",  # O'tish/Kirish
        r"\b(bog'lanish|bog'laning|aloqa|contact)\b",  # Bog'lanish
        r"\b(olish|oling|qo'lga kiriting)\b",  # Olish
        r"\b(buyurtma|buyurtma berish|order|zakaz)\b",  # Buyurtma
    ]
    
    if any(re.search(p, text_lower) for p in cta_patterns):
        return True
    
    # 7. Foiz va chegirma belgilari (50%, 100% chegirma va hokazo)
    if re.search(r"\d+%\s*(chegirma|скидка|discount|skidka)", text_lower):
        return True
    
    # 8. "Top N" yoki "Top-10" kabi iboralar
    if re.search(r"top\s*[-]?\s*\d+", text_lower):
        return True
    
    # 9. Rasmiy reklama belgilari
    sponsored_keywords = [
        "sponsored", "реклама", "homiy", "рекламный",
        "advertisement", "ad", "ads", "реклама"
    ]
    
    if any(k in text_lower for k in sponsored_keywords):
        return True
    
    # 10. "Faqat bugun", "Oxirgi imkoniyat" kabi urg'uli iboralar
    urgent_patterns = [
        r"faqat\s+(bugun|hozir|shu\s+vaqt)",  # Faqat bugun/hozir
        r"oxirgi\s+imkoniyat",  # Oxirgi imkoniyat
        r"limited\s+time",  # Limited time
        r"только\s+сегодня",  # Только сегодня
        r"последний\s+шанс",  # Последний шанс
    ]
    
    if any(re.search(p, text_lower) for p in urgent_patterns):
        return True
    
    return False

@router.message(F.chat.type.in_(["group", "supergroup"]), flags={"block": False})
async def anti_advertisement_guard(message: Message):
    """Reklama xabarlarini o'chirish va ogohlantirish"""
    # Bot xabarlari va botlar e'tiborsiz qoldiriladi
    if not message.from_user or message.from_user.is_bot:
        return
    
    # Buyruqlarni (commands) e'tiborsiz qoldirish - ular boshqa handlerlarga o'tishi kerak
    if message.text and message.text.startswith("/"):
        return
    
    # Bot adminlari (config.ADMIN_ID) e'tiborsiz qoldiriladi
    if is_admin(message.from_user.id):
        return
    
    # Guruh adminlari ham e'tiborsiz qoldiriladi
    if await is_group_admin(message.bot, message.chat.id, message.from_user.id):
        return

    # Botning xabarlarni o'chirish huquqini tekshirish
    can_delete = await can_bot_delete_messages(message.bot, message.chat.id)
    if not can_delete:
        logger.warning(f"Bot guruhda xabarlarni o'chirish huquqiga ega emas: {message.chat.id}")
        return

    # Forward qilingan kanal postlari (reklama sifatida qabul qilinadi)
    if getattr(message, 'forward_from_chat', None) and getattr(message.forward_from_chat, 'type', None) == 'channel':
        try:
            await message.reply(
                f"⚠️ {message.from_user.full_name}, bu guruhda reklama taqiqlangan. Xabaringiz o'chirildi."
            )
        except Exception as e:
            logger.error(f"Ogohlantirish yuborishda xatolik: {e}")
        
        if can_delete:
            try:
                await message.delete()
                logger.info(f"Forward qilingan reklama o'chirildi: chat_id={message.chat.id}, user_id={message.from_user.id}")
            except Exception as e:
                logger.error(f"Xabarni o'chirishda xatolik: {e}")
        return

    # Matn yoki caption ni tekshirish
    text_to_check = message.text or message.caption or ""
    has_advertisement = contains_advertisement(text_to_check)
    
    # Entities orqali linklar va mentionlarni tekshirish
    if not has_advertisement and message.entities:
        for ent in message.entities:
            if ent.type in ["url", "text_link", "mention"]:
                has_advertisement = True
                break
    
    # Caption entities orqali linklar va mentionlarni tekshirish
    if not has_advertisement and message.caption_entities:
        for ent in message.caption_entities:
            if ent.type in ["url", "text_link", "mention"]:
                has_advertisement = True
                break

    # Agar reklama topilsa, xabarni o'chirish
    if has_advertisement:
        logger.info(f"Reklama aniqlandi: chat_id={message.chat.id}, user_id={message.from_user.id}, text={text_to_check[:50]}")
        try:
            await message.reply(
                f"⚠️ {message.from_user.full_name}, reklama tarqatish mumkin emas. Xabaringiz o'chirildi."
            )
        except Exception as e:
            logger.error(f"Ogohlantirish yuborishda xatolik: {e}")
        
        if can_delete:
            try:
                await message.delete()
                logger.info(f"Reklama o'chirildi: chat_id={message.chat.id}, user_id={message.from_user.id}")
            except Exception as e:
                logger.error(f"Xabarni o'chirishda xatolik: {e}")
        return


