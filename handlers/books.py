"""
Kitob qidirish va yuklash handlerlari
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter
from aiogram.exceptions import TelegramRetryAfter
from database.db import Database
from utils.helpers import get_file_type, clean_filename, extract_book_info, validate_file_size, escape_markdown, format_file_size, is_admin
from utils.subscription import is_subscribed_to_all, get_subscription_message_async
import config
import asyncio
import re

router = Router()
# Guruhlarda ham ishlashi uchun filter olib tashlandi
db = Database()

async def safe_reply_or_send(message: Message, text: str, reply_markup=None, parse_mode=None):
    """Guruhlarda xavfsiz javob berish funksiyasi (reply qiladi)"""
    try:
        print(f"DEBUG: safe_reply_or_send - chat_type={message.chat.type}, chat_id={message.chat.id}, text_length={len(text)}")
        if message.chat.type in ["group", "supergroup"]:
            # Guruhlarda reply qilib javob beramiz
            try:
                await message.reply(text, reply_markup=reply_markup, parse_mode=parse_mode)
                print(f"DEBUG: Xabar guruhga reply qilib muvaffaqiyatli yuborildi")
            except Exception as reply_error:
                # Agar reply ishlamasa, oddiy send_message ishlatamiz
                print(f"DEBUG: Reply ishlamadi, oddiy yuborishga o'tilmoqda: {reply_error}")
                await message.bot.send_message(
                    chat_id=message.chat.id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
                print(f"DEBUG: Xabar guruhga oddiy usulda muvaffaqiyatli yuborildi")
        else:
            await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
            print(f"DEBUG: Xabar shaxsiy chatga muvaffaqiyatli yuborildi")
    except Exception as e:
        print(f"DEBUG: safe_reply_or_send xatolik: {e}")
        import traceback
        traceback.print_exc()
        # Xatolikni qaytaramiz, chunki funksiya exception qaytarishi kerak
        raise

async def retry_with_delay(func, max_retries=3, delay=5):
    """Flood control xatoliklarini hal qilish uchun retry funksiyasi"""
    for attempt in range(max_retries):
        try:
            return await func()
        except TelegramRetryAfter as e:
            wait_time = e.retry_after
            if attempt < max_retries - 1:
                await asyncio.sleep(wait_time)
                continue
            else:
                raise
        except Exception as e:
            error_str = str(e)
            # Flood control xatoligini aniqlash
            if "Flood control" in error_str or "Too Many Requests" in error_str or "retry after" in error_str:
                # Retry after soniyalarini olish
                match = re.search(r'retry after (\d+)', error_str, re.IGNORECASE)
                if match:
                    wait_time = int(match.group(1))
                else:
                    wait_time = delay
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time + 1)  # Qo'shimcha 1 soniya kutamiz
                    continue
                else:
                    raise
            else:
                raise
    return None

class BookStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_author = State()
    waiting_for_description = State()
    auto_upload_mode = State()
    multi_part_title = State()
    multi_part_collecting = State()

@router.callback_query(F.data == "add_multi_part_book")
async def add_multi_part_book_callback(callback: CallbackQuery, state: FSMContext):
    """Bir kitob uchun bir nechta qism qo'shish rejimini ishga tushirish"""
    await state.clear()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")]
    ])
    await callback.message.edit_text(
        "🧩 *Qismli kitob qo'shish rejimi*\n\n"
        "1. Avval kitob nomini yuboring.\n"
        "2. So'ngra E-kitob (PDF, DOCX, XLSX, ...) yoki Audio (MP3, WAV, ...) fayllarni aralash tarzda yuboring.\n"
        "3. Har bir fayl avtomatik ravishda tegishli turga joylanadi.\n"
        "4. Tugatgach \"✅ Yakunlash\" tugmasini bosing.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await state.set_state(BookStates.multi_part_title)

async def is_group_admin(bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except Exception:
        return False

async def is_user_allowed_to_post(bot, chat_id: int, user_id: int) -> bool:
    """Foydalanuvchiga reklama yuborishga ruxsat bor-yo'qligini tekshirish"""
    # Admin va botning o'zi har doim ruxsat etiladi
    if is_admin(user_id) or user_id == bot.id:
        return True
    
    # Guruh adminlari ham ruxsat etiladi
    if await is_group_admin(bot, chat_id, user_id):
        return True
    
    # Biriktirilgan kanallar tekshiruvi
    try:
        required_channels = db.get_required_channels()
        for channel in required_channels:
            channel_id = channel.get('channel_id')
            if not channel_id:
                continue
            
            try:
                # Kanal a'zosi ekanligini tekshirish
                member = await bot.get_chat_member(channel_id, user_id)
                if member.status in ["member", "administrator", "creator"]:
                    return True
            except Exception:
                continue
    except Exception:
        pass
    
    return False

def contains_advertisement(text: str) -> bool:
    if not text:
        return False
    text_lower = text.lower()
    patterns = [
        r"https?://",
        r"\bt\.me/",
        r"\bt\.me/c/\d+/\d+",
        r"joinchat/",
        r"\+[a-zA-Z0-9_-]{10,}",
        r"\.(com|uz|ru|org|net|info|io|me)\b",
        r"@[a-zA-Z0-9_]{5,}",
        r"\b\d{2,3}[-\s]??\d{2,3}[-\s]??\d{2}[-\s]?\d{2}\b",
        r"\b\d{7,}\b",
        r"\b\d+%\b",
        r"[₩¥$€£]",
    ]
    if any(re.search(p, text_lower) for p in patterns):
        return True
    keywords = [
        "reklama", "aksiya", "chegirma", "arzon", "sotuv", "bonus",
        "kurs", "dars", "jonli dars", "videodars", "kanalimizda",
        "murojaat uchun", "bog'lanish uchun", "obuna", "promo",
        "skidka", "akciya", "rasprodaja", "скидка", "акция",
        "реклама", "подпишитесь", "subscribe", "join our channel"
    ]
    return any(k in text_lower for k in keywords)

@router.message(StateFilter(None), F.text)
async def search_books(message: Message, state: FSMContext):
    """Kitob qidirish"""
    chat = message.chat
    user = message.from_user
    
    # Agar guruh bo'lsa, guruhni ma'lumotlar bazasiga qo'shish
    if chat.type in ["group", "supergroup"]:
        db.add_group(
            group_id=chat.id,
            title=chat.title or "Noma'lum",
            group_type=chat.type
        )
        # Foydalanuvchini ham qo'shish
        db.add_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            is_bot=user.is_bot,
            language_code=user.language_code
        )
    
    # Agar boshqa state faol bo'lsa, qidirishni o'tkazib yuborish
    current_state = await state.get_state()
    
    # Kanal qo'shish state ni tekshirish
    if current_state:
        from handlers.admin import ChannelStates
        # State nomini solishtirish (instance emas, nom bo'yicha)
        state_name = str(current_state) if current_state else None
        
        if current_state == ChannelStates.waiting_for_channel:
            return  # Kanal qo'shish handleriga o'tkazish
        
        # Kitob qo'shish state larni tekshirish
        if current_state in [
            BookStates.waiting_for_title,
            BookStates.waiting_for_author,
            BookStates.waiting_for_description,
            BookStates.auto_upload_mode,
            BookStates.multi_part_title,
            BookStates.multi_part_collecting
        ]:
            return  # Kitob qo'shish handlerlariga o'tkazish
    
    # Reklama tekshiruvi groups.router da amalga oshiriladi

    # Majburiy obuna tekshirish
    if not await is_subscribed_to_all(message.bot, message.from_user.id):
        msg_text, keyboard = await get_subscription_message_async(message.bot)
        await safe_reply_or_send(message, msg_text, reply_markup=keyboard)
        return
    
    query = message.text.strip()
    
    if len(query) < 1:
        await safe_reply_or_send(message, "❌ Qidirish so'zi kamida 2 ta belgidan iborat bo'lishi kerak.")
        return
    
    try:
        print(f"DEBUG: Qidirish boshlandi - query='{query}', chat_id={message.chat.id}, chat_type={message.chat.type}")
        books = db.search_books(query)
        print(f"DEBUG: Qidirish '{query}' uchun {len(books)} ta natija topildi")
        
        if not books:
            text = f"🔍 '{query}' so'zi bo'yicha kitoblar topilmadi.\n\nBoshqa kalit so'zlar bilan qidirib ko'ring."
            print(f"DEBUG: Natija topilmadi, xabar yuborilmoqda")
            await safe_reply_or_send(message, text)
            print(f"DEBUG: Xabar yuborildi (natija topilmadi)")
            return
        
        if len(books) == 1:
            # Agar bitta kitob topilsa, to'g'ridan-to'g'ri yuborish
            print(f"DEBUG: Bitta kitob topildi, yuborilmoqda")
            book = books[0]
            await send_book(message, book)
            print(f"DEBUG: Kitob yuborildi")
        else:
            # Agar bir nechta kitob topilsa, ro'yxat ko'rsatish
            print(f"DEBUG: {len(books)} ta kitob topildi, ro'yxat ko'rsatilmoqda")
            await show_search_results(message, books, query, page=0, state=state)
            print(f"DEBUG: Ro'yxat ko'rsatildi")
    
    except Exception as e:
        print(f"DEBUG: Qidirishda xatolik: {e}")
        import traceback
        traceback.print_exc()
        try:
            await safe_reply_or_send(message, f"❌ Qidirishda xatolik yuz berdi: {str(e)}")
        except Exception as e2:
            print(f"DEBUG: Xatolik xabarini yuborishda ham xatolik: {e2}")


async def send_book(message: Message, book: dict):
    """Kitobni yuborish"""
    is_group = message.chat.type in ["group", "supergroup"]
    reply_to_id = message.message_id if is_group else None
    
    if book.get('is_multi_part'):
        await send_multi_part_choice(
            bot=message.bot,
            chat_id=message.chat.id,
            book=book,
            reply_to_message_id=reply_to_id  # Guruhlarda reply qilamiz
        )
        return
    try:
        # Agar saqlash xabari ma'lum bo'lsa, uni nusxalashga harakat qilamiz
        if book.get('storage_message_id') and (book.get('storage_chat_id') or config.STORAGE_CHANNEL_ID):
            from_chat = book.get('storage_chat_id') or config.STORAGE_CHANNEL_ID
            try:
                await message.bot.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=from_chat,
                    message_id=book['storage_message_id'],
                    caption=f"📖 **{escape_markdown(book['title'])}**\n\n"
                            f"👤 Muallif: {escape_markdown(book['author'] or 'Noma\'lum')}\n"
                            f"📁 Turi: {book['file_type']}\n"
                            f"💾 Hajmi: {format_file_size(book['file_size'])}\n"
                            f"📅 Yuklangan: {book['upload_date'][:10]}",
                    parse_mode="Markdown",
                    reply_to_message_id=reply_to_id  # Guruhlarda reply qilamiz
                )
                return  # Muvaffaqiyatli yuborildi
            except Exception as copy_error:
                # Agar copy_message ishlamasa, file_id orqali yuboramiz
                print(f"DEBUG: copy_message xatolik, file_id orqali yuborilmoqda: {copy_error}")
                pass  # Fallback ga o'tamiz
        
        # Fallback: file_id orqali yuborish
        try:
            if book['file_type'] == 'document':
                await message.bot.send_document(
                    chat_id=message.chat.id,
                    document=book['file_id'],
                    caption=f"📖 **{escape_markdown(book['title'])}**\n\n"
                           f"👤 Muallif: {escape_markdown(book['author'] or 'Noma\'lum')}\n"
                           f"📁 Turi: {book['file_type']}\n"
                           f"💾 Hajmi: {format_file_size(book['file_size'])}\n"
                           f"📅 Yuklangan: {book['upload_date'][:10]}",
                    parse_mode="Markdown",
                    reply_to_message_id=reply_to_id  # Guruhlarda reply qilamiz
                )
            elif book['file_type'] == 'audio':
                await message.bot.send_audio(
                    chat_id=message.chat.id,
                    audio=book['file_id'],
                    caption=f"🎵 **{escape_markdown(book['title'])}**\n\n"
                           f"👤 Muallif: {escape_markdown(book['author'] or 'Noma\'lum')}\n"
                           f"📁 Turi: {book['file_type']}\n"
                           f"💾 Hajmi: {format_file_size(book['file_size'])}\n"
                           f"📅 Yuklangan: {book['upload_date'][:10]}",
                    parse_mode="Markdown",
                    reply_to_message_id=reply_to_id  # Guruhlarda reply qilamiz
                )
        except Exception as send_error:
            error_str = str(send_error).lower()
            if "not enough rights" in error_str or "can't send" in error_str or "permission" in error_str:
                # Botda huquq yo'q, shaxsiy chatga yuborishni taklif qilamiz
                error_msg = (
                    "❌ Botda guruhda hujjat yuborish huquqi yo'q.\n\n"
                    "📋 **Yechim:**\n"
                    "1. Botni guruhga admin qiling\n"
                    "2. Botga 'Post messages' va 'Send messages' huquqlarini bering\n"
                    "3. Yoki botga shaxsiy xabar yuboring: /start\n\n"
                    f"📖 **Kitob:** {escape_markdown(book['title'])}\n"
                    f"👤 **Muallif:** {escape_markdown(book['author'] or 'Noma\'lum')}"
                )
                await safe_reply_or_send(message, error_msg, parse_mode="Markdown")
            else:
                # Boshqa xatolik
                await safe_reply_or_send(message, f"❌ Kitob yuborishda xatolik: {str(send_error)}")
    except Exception as e:
        error_str = str(e).lower()
        if "not enough rights" in error_str or "can't send" in error_str or "permission" in error_str:
            error_msg = (
                "❌ Botda guruhda hujjat yuborish huquqi yo'q.\n\n"
                "📋 **Yechim:**\n"
                "1. Botni guruhga admin qiling\n"
                "2. Botga 'Post messages' va 'Send messages' huquqlarini bering\n"
                "3. Yoki botga shaxsiy xabar yuboring: /start"
            )
            await safe_reply_or_send(message, error_msg, parse_mode="Markdown")
        else:
            await safe_reply_or_send(message, f"❌ Kitob yuborishda xatolik yuz berdi: {str(e)}")

async def update_search_results(callback: CallbackQuery, books: list, query: str, page: int, state: FSMContext):
    """Sahifalash uchun natijalarni yangilash"""
    # show_search_results bilan bir xil, lekin edit_text ishlatadi
    items_per_page = 10
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_books = books[start_idx:end_idx]
    total_pages = (len(books) + items_per_page - 1) // items_per_page
    
    results_text = f"🔍 Qidiruv natijalari:\n\n"
    
    for i, book in enumerate(page_books, 1):
        global_idx = start_idx + i
        title = escape_markdown(book['title'])
        author = escape_markdown(book['author'] or "Noma'lum")
        
        if len(title) > 75:
            title = title[:72] + "..."
        
        suffix = " 🧩" if book.get('is_multi_part') else ""
        results_text += f"{global_idx}. **{title}**{suffix}\n"
        if author != "Noma'lum":
            results_text += f"   {author}\n"
        results_text += "\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    first_row = []
    for i in range(1, min(6, len(page_books) + 1)):
        global_idx = start_idx + i
        first_row.append(InlineKeyboardButton(
            text=str(global_idx),
            callback_data=f"send_book_{books[start_idx + i - 1]['id']}"
        ))
    if first_row:
        keyboard.inline_keyboard.append(first_row)
    
    if len(page_books) > 5:
        second_row = []
        for i in range(6, min(11, len(page_books) + 1)):
            global_idx = start_idx + i
            second_row.append(InlineKeyboardButton(
                text=str(global_idx),
                callback_data=f"send_book_{books[start_idx + i - 1]['id']}"
            ))
        if second_row:
            keyboard.inline_keyboard.append(second_row)
    
    if state:
        await state.update_data(last_search_query=query)
    
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"search_page_{page - 1}"))
        nav_buttons.append(InlineKeyboardButton(text="❌", callback_data="close_search"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"search_page_{page + 1}"))
        keyboard.inline_keyboard.append(nav_buttons)
    else:
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="❌ Yopish", callback_data="close_search")])
    
    await callback.message.edit_text(results_text, parse_mode="Markdown", reply_markup=keyboard)

async def show_search_results(message: Message, books: list, query: str, page: int = 0, state: FSMContext = None):
    """Qidirish natijalarini ko'rsatish (rasmdagidek format)"""
    try:
        print(f"DEBUG: show_search_results chaqirildi - books={len(books)}, page={page}")
        # Har bir sahifada 10 ta kitob
        items_per_page = 10
        start_idx = page * items_per_page
        end_idx = start_idx + items_per_page
        page_books = books[start_idx:end_idx]
        total_pages = (len(books) + items_per_page - 1) // items_per_page
        
        # Sarlavha
        results_text = f"🔍 Qidiruv natijalari:\n\n"
        
        # Kitoblar ro'yxati
        for i, book in enumerate(page_books, 1):
            global_idx = start_idx + i
            title = escape_markdown(book['title'])
            author = escape_markdown(book['author'] or "Noma'lum")
            
            # Kitob nomini to'liq ko'rsatish (75 belgigacha)
            if len(title) > 75:
                title = title[:72] + "..."
            
            suffix = " 🧩" if book.get('is_multi_part') else ""
            results_text += f"{global_idx}. **{title}**{suffix} {author}\n"
            # if author != "Noma'lum":
            #     results_text += f"   {author}\n"
        
        # Keyboard yaratish
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        
        # Birinchi qator tugmalar (1-5)
        first_row = []
        for i in range(1, min(6, len(page_books) + 1)):
            global_idx = start_idx + i
            first_row.append(InlineKeyboardButton(
                text=str(global_idx),
                callback_data=f"send_book_{books[start_idx + i - 1]['id']}"
            ))
        if first_row:
            keyboard.inline_keyboard.append(first_row)
        
        # Ikkinchi qator tugmalar (6-10)
        if len(page_books) > 5:
            second_row = []
            for i in range(6, min(11, len(page_books) + 1)):
                global_idx = start_idx + i
                second_row.append(InlineKeyboardButton(
                    text=str(global_idx),
                    callback_data=f"send_book_{books[start_idx + i - 1]['id']}"
                ))
            if second_row:
                keyboard.inline_keyboard.append(second_row)
        
        # Query ni state ga saqlash (sahifalash uchun)
        if state:
            await state.update_data(last_search_query=query)
        
        # Navigatsiya tugmalari (faqat bir nechta sahifa bo'lsa)
        if total_pages > 1:
            nav_buttons = []
            if page > 0:
                nav_buttons.append(InlineKeyboardButton(
                    text="◀️",
                    callback_data=f"search_page_{page - 1}"
                ))
            nav_buttons.append(InlineKeyboardButton(
                text="❌",
                callback_data="close_search"
            ))
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton(
                    text="▶️",
                    callback_data=f"search_page_{page + 1}"
                ))
            keyboard.inline_keyboard.append(nav_buttons)
        else:
            # Yopish tugmasi
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="❌ Yopish", callback_data="close_search")
            ])
        
        print(f"DEBUG: Xabar yuborilmoqda - chat_id={message.chat.id}, text_length={len(results_text)}")
        await safe_reply_or_send(message, results_text, reply_markup=keyboard, parse_mode="Markdown")
        print(f"DEBUG: Xabar muvaffaqiyatli yuborildi")
    except Exception as e:
        print(f"DEBUG: show_search_results xatolik: {e}")
        import traceback
        traceback.print_exc()
        try:
            await safe_reply_or_send(message, f"❌ Natijalarni ko'rsatishda xatolik yuz berdi: {str(e)}")
        except Exception as e2:
            print(f"DEBUG: Xatolik xabarini yuborishda ham xatolik: {e2}")

@router.callback_query(F.data.startswith("search_page_"))
async def search_page_callback(callback: CallbackQuery, state: FSMContext):
    """Sahifalash callback"""
    # Format: search_page_{page}
    # Query ni state dan olamiz yoki callback data dan
    try:
        # Sahifani olish
        page_str = callback.data.replace("search_page_", "")
        page = int(page_str)
        
        # Query ni state dan olish
        state_data = await state.get_data()
        query = state_data.get('last_search_query', '')
        
        if not query:
            await callback.answer("❌ Qidiruv ma'lumoti topilmadi!")
            return
        
        books = db.search_books(query)
        if not books:
            await callback.answer("❌ Natijalar topilmadi!")
            return
        
        # Natijalarni yangilash
        await update_search_results(callback, books, query, page, state)
        await callback.answer()
    except ValueError:
        await callback.answer("❌ Noto'g'ri sahifa raqami!")
    except Exception as e:
        await callback.answer(f"❌ Xatolik: {str(e)}")

@router.callback_query(F.data == "close_search")
async def close_search_callback(callback: CallbackQuery):
    """Qidiruv natijalarini yopish"""
    await callback.message.delete()
    await callback.answer("✅ Yopildi")

@router.callback_query(F.data.startswith("send_book_"))
async def send_book_callback(callback: CallbackQuery):
    """Callback orqali kitob yuborish"""
    book_id = int(callback.data.split("_")[2])
    book = db.get_book_by_id(book_id)
    
    if not book:
        await callback.answer("❌ Kitob topilmadi!")
        return

    if book.get('is_multi_part'):
        await send_multi_part_choice(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            book=book,
            reply_to_message_id=None  # Guruhlarda ham reply qilmaymiz
        )
        await callback.answer("🔽 Fayl turini tanlang")
        return
    
    try:
        # Avval nusxalashga harakat qilamiz
        if book.get('storage_message_id') and (book.get('storage_chat_id') or config.STORAGE_CHANNEL_ID):
            from_chat = book.get('storage_chat_id') or config.STORAGE_CHANNEL_ID
            try:
                await callback.bot.copy_message(
                    chat_id=callback.message.chat.id,
                    from_chat_id=from_chat,
                    message_id=book['storage_message_id'],
                    caption=f"📖 **{escape_markdown(book['title'])}**\n\n"
                            f"👤 Muallif: {escape_markdown(book['author'] or 'Noma\'lum')}\n"
                            f"📁 Turi: {book['file_type']}\n"
                            f"💾 Hajmi: {format_file_size(book['file_size'])}\n"
                            f"📅 Yuklangan: {book['upload_date'][:10]}",
                    parse_mode="Markdown",
                    reply_to_message_id=None  # Guruhlarda ham reply qilmaymiz
                )
                await callback.answer("✅ Kitob yuborildi!")
                return  # Muvaffaqiyatli yuborildi
            except Exception as copy_error:
                # Agar copy_message ishlamasa, file_id orqali yuboramiz
                print(f"DEBUG: copy_message xatolik, file_id orqali yuborilmoqda: {copy_error}")
                pass  # Fallback ga o'tamiz
        
        # Fallback file_id orqali
        try:
            if book['file_type'] == 'document':
                await callback.bot.send_document(
                    chat_id=callback.message.chat.id,
                    document=book['file_id'],
                    caption=f"📖 **{escape_markdown(book['title'])}**\n\n"
                           f"👤 Muallif: {escape_markdown(book['author'] or 'Noma\'lum')}\n"
                           f"📁 Turi: {book['file_type']}\n"
                           f"💾 Hajmi: {format_file_size(book['file_size'])}\n"
                           f"📅 Yuklangan: {book['upload_date'][:10]}",
                    parse_mode="Markdown",
                    reply_to_message_id=None  # Guruhlarda ham reply qilmaymiz
                )
            elif book['file_type'] == 'audio':
                await callback.bot.send_audio(
                    chat_id=callback.message.chat.id,
                    audio=book['file_id'],
                    caption=f"🎵 **{escape_markdown(book['title'])}**\n\n"
                           f"👤 Muallif: {escape_markdown(book['author'] or 'Noma\'lum')}\n"
                           f"📁 Turi: {book['file_type']}\n"
                           f"💾 Hajmi: {format_file_size(book['file_size'])}\n"
                           f"📅 Yuklangan: {book['upload_date'][:10]}",
                    parse_mode="Markdown",
                    reply_to_message_id=None  # Guruhlarda ham reply qilmaymiz
                )
            
            await callback.answer("✅ Kitob yuborildi!")
        except Exception as send_error:
            error_str = str(send_error).lower()
            if "not enough rights" in error_str or "can't send" in error_str or "permission" in error_str:
                error_msg = (
                    "❌ Botda guruhda hujjat yuborish huquqi yo'q.\n\n"
                    "📋 Yechim:\n"
                    "1. Botni guruhga admin qiling\n"
                    "2. Botga 'Post messages' va 'Send messages' huquqlarini bering\n"
                    "3. Yoki botga shaxsiy xabar yuboring: /start"
                )
                await callback.message.answer(error_msg)
                await callback.answer("❌ Huquq yo'q", show_alert=True)
            else:
                await callback.answer(f"❌ Xatolik: {str(send_error)}", show_alert=True)
    except Exception as e:
        error_str = str(e).lower()
        if "not enough rights" in error_str or "can't send" in error_str or "permission" in error_str:
            error_msg = (
                "❌ Botda guruhda hujjat yuborish huquqi yo'q.\n\n"
                "📋 Yechim:\n"
                "1. Botni guruhga admin qiling\n"
                "2. Botga 'Post messages' va 'Send messages' huquqlarini bering\n"
                "3. Yoki botga shaxsiy xabar yuboring: /start"
            )
            await callback.message.answer(error_msg)
            await callback.answer("❌ Huquq yo'q", show_alert=True)
        else:
            await callback.answer(f"❌ Xatolik: {str(e)}", show_alert=True)

@router.message(F.document | F.audio)
async def handle_file_upload(message: Message, state: FSMContext):
    """Fayl yuklash"""
    # Admin buyruqlari faqat shaxsiy chatda ishlaydi
    if message.chat.type != "private":
        return  # Guruhlarda fayl yuklashni e'tiborsiz qoldirish
    
    # Faqat admin fayl yuklashi mumkin
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin fayl yuklashi mumkin!")
        return
    
    current_state = await state.get_state()
    
    file = message.document or message.audio
    filename = file.file_name or "unknown"
    
    # Fayl turini tekshirish
    file_type = get_file_type(filename)
    if not file_type:
        await message.answer(f"❌ Ruxsat etilmagan fayl turi: {filename}\n\nQo'llab-quvvatlanadigan formatlar: PDF, DOCX, MP3, WAV, OGG, M4A, FLAC")
        return
    
    # Fayl hajmini tekshirish
    if not validate_file_size(file.file_size):
        await message.answer(f"❌ Fayl hajmi juda katta! Maksimal hajm: {config.MAX_FILE_SIZE} MB")
        return
    
    status_msg = None
    storage_chat_id = str(config.STORAGE_CHANNEL_ID)
    try:
        # Foydalanuvchiga yuklash boshlanganini xabar qilish
        status_msg = await message.answer("📤 Fayl yuklanmoqda...")
        
        # Faylni saqlash kanaliga yuklash (retry mexanizmi bilan)
        sent_message = None
        if file_type == 'document':
            async def send_doc():
                return await message.bot.send_document(
                    chat_id=config.STORAGE_CHANNEL_ID,
                    document=file.file_id,
                    caption=f"📚 {filename}"
                )
            
            # Retry mexanizmi bilan yuklash
            try:
                sent_message = await send_doc()
            except Exception as e:
                error_str = str(e)
                if "Flood control" in error_str or "Too Many Requests" in error_str or "retry after" in error_str:
                    match = re.search(r'retry after (\d+)', error_str, re.IGNORECASE)
                    wait_time = int(match.group(1)) if match else 5
                    await status_msg.edit_text(f"⏳ Telegram limitiga duch keldik. {wait_time} soniyadan keyin qayta urinilmoqda...")
                    await asyncio.sleep(wait_time + 1)
                    sent_message = await send_doc()
                else:
                    raise
            
            file_id = sent_message.document.file_id
            storage_message_id = sent_message.message_id
        elif file_type == 'audio':
            async def send_aud():
                return await message.bot.send_audio(
                    chat_id=config.STORAGE_CHANNEL_ID,
                    audio=file.file_id,
                    caption=f"🎵 {filename}"
                )
            
            # Retry mexanizmi bilan yuklash
            try:
                sent_message = await send_aud()
            except Exception as e:
                error_str = str(e)
                if "Flood control" in error_str or "Too Many Requests" in error_str or "retry after" in error_str:
                    match = re.search(r'retry after (\d+)', error_str, re.IGNORECASE)
                    wait_time = int(match.group(1)) if match else 5
                    await status_msg.edit_text(f"⏳ Telegram limitiga duch keldik. {wait_time} soniyadan keyin qayta urinilmoqda...")
                    await asyncio.sleep(wait_time + 1)
                    sent_message = await send_aud()
                else:
                    raise
            
            file_id = sent_message.audio.file_id
            storage_message_id = sent_message.message_id
        
        # Status xabarini o'chirish
        await status_msg.delete()
        
        if current_state == BookStates.multi_part_collecting:
            await process_multi_part_uploaded_file(
                message=message,
                state=state,
                filename=filename,
                file_id=file_id,
                file_type=file_type,
                file_size=file.file_size,
                storage_message_id=storage_message_id,
                storage_chat_id=storage_chat_id
            )
            return
        
        # Avtomatik yuklash rejimi tekshirish
        if current_state == BookStates.auto_upload_mode:
            # Avtomatik ravishda kitob ma'lumotlarini aniqlash
            title, author = extract_book_info(filename)
            
            # Kitobni ma'lumotlar bazasiga qo'shish
            success = db.add_book(
                title=title,
                author=author,
                file_id=file_id,
                file_type=file_type,
                file_size=file.file_size,
                uploader_id=message.from_user.id,
                description=f"Avtomatik yuklangan: {filename}",
                storage_message_id=storage_message_id,
                storage_chat_id=storage_chat_id
            )
            
            if success:
                await message.answer(f"✅ **Avtomatik qo'shildi!**\n\n"
                                   f"📖 **{title}**\n"
                                   f"👤 Muallif: {author}\n"
                                   f"📁 Turi: {file_type}\n"
                                   f"💾 Hajmi: {format_file_size(file.file_size)}\n\n"
                                   f"Yana fayl yuklang yoki /stop buyrug'ini yuboring.")
            else:
                await message.answer(f"❌ Kitob qo'shishda xatolik!")
        
        else:
            # Oddiy yuklash rejimi
            await state.update_data(
                file_id=file_id,
                file_type=file_type,
                file_size=file.file_size,
                filename=filename,
                storage_message_id=storage_message_id,
                storage_chat_id=storage_chat_id
            )
            
            # Kitob nomini so'rash
            await message.answer("📚 Kitob nomini kiriting:")
            await state.set_state(BookStates.waiting_for_title)
        
    except Exception as e:
        # Status xabarini o'chirish (agar mavjud bo'lsa)
        if status_msg:
            try:
                await status_msg.delete()
            except:
                pass
        
        error_str = str(e)
        if "Flood control" in error_str or "Too Many Requests" in error_str or "retry after" in error_str:
            # Retry after soniyalarini olish
            match = re.search(r'retry after (\d+)', error_str, re.IGNORECASE)
            if match:
                wait_time = int(match.group(1))
                await message.answer(f"⚠️ Telegram limitiga duch keldik.\n\n"
                                   f"⏳ {wait_time} soniyadan keyin qayta urinib ko'ring.\n\n"
                                   f"Bu holat ko'p fayl yuklanganda yuzaga keladi. Biroz sabr qiling.")
            else:
                await message.answer(f"⚠️ Telegram limitiga duch keldik.\n\n"
                                   f"Bir necha soniyadan keyin qayta urinib ko'ring.\n\n"
                                   f"Bu holat ko'p fayl yuklanganda yuzaga keladi.")
        else:
            await message.answer(f"❌ Fayl yuklashda xatolik: {str(e)}")

@router.message(BookStates.waiting_for_title)
async def process_title(message: Message, state: FSMContext):
    """Kitob nomini qabul qilish"""
    title = message.text.strip()
    
    if len(title) < 2:
        await message.answer("❌ Kitob nomi kamida 2 ta belgidan iborat bo'lishi kerak.")
        return
    
    await state.update_data(title=title)
    await message.answer("👤 Muallif nomini kiriting (ixtiyoriy):")
    await state.set_state(BookStates.waiting_for_author)

@router.message(BookStates.waiting_for_author)
async def process_author(message: Message, state: FSMContext):
    """Muallif nomini qabul qilish"""
    author = message.text.strip() if message.text else "Noma'lum"
    
    await state.update_data(author=author)
    await message.answer("📝 Kitob haqida qisqacha ma'lumot kiriting (ixtiyoriy):")
    await state.set_state(BookStates.waiting_for_description)

@router.message(BookStates.waiting_for_description)
async def process_description(message: Message, state: FSMContext):
    """Tavsifni qabul qilish va kitobni saqlash"""
    description = message.text.strip() if message.text else ""
    
    data = await state.get_data()
    
    # Kitobni ma'lumotlar bazasiga qo'shish
    success = db.add_book(
        title=data['title'],
        author=data['author'],
        file_id=data['file_id'],
        file_type=data['file_type'],
        file_size=data['file_size'],
        uploader_id=message.from_user.id,
        description=description,
        storage_message_id=data.get('storage_message_id'),
        storage_chat_id=data.get('storage_chat_id')
    )
    
    if success:
        await message.answer(f"✅ Kitob muvaffaqiyatli qo'shildi!\n\n"
                           f"📖 **{data['title']}**\n"
                           f"👤 Muallif: {data['author']}\n"
                           f"📁 Turi: {data['file_type']}\n"
                           f"💾 Hajmi: {format_file_size(data['file_size'])}")
    else:
        await message.answer("❌ Kitob qo'shishda xatolik yuz berdi!")
    
    await state.clear()

async def process_multi_part_uploaded_file(
    message: Message,
    state: FSMContext,
    filename: str,
    file_id: str,
    file_type: str,
    file_size: int,
    storage_message_id: int | None,
    storage_chat_id: str | None
):
    """Qismli kitob uchun ketma-ket fayllarni saqlash"""
    data = await state.get_data()
    title = data.get('multi_title')
    if not title:
        await message.answer("❌ Avval kitob nomini kiriting.")
        await state.set_state(BookStates.multi_part_title)
        return
    author = data.get('multi_author', "Noma'lum")
    description = data.get('multi_description', "Qismli kitob")
    book_id = data.get('book_id')
    if not book_id:
        book_id = db.add_book(
            title=title,
            author=author,
            file_id=file_id,
            file_type=file_type,
            file_size=file_size,
            uploader_id=message.from_user.id,
            description=description,
            storage_message_id=storage_message_id,
            storage_chat_id=storage_chat_id,
            is_multi_part=True
        )
        if not book_id:
            await message.answer("❌ Kitobni yaratishda xatolik yuz berdi.")
            return
        await state.update_data(book_id=book_id)
    else:
        saved = db.add_book_file(
            book_id=book_id,
            file_id=file_id,
            file_type=file_type,
            file_size=file_size,
            storage_message_id=storage_message_id,
            storage_chat_id=storage_chat_id
        )
        if not saved:
            await message.answer("❌ Faylni saqlashda xatolik yuz berdi.")
            return
    doc_parts = db.get_book_files(book_id, 'document')
    audio_parts = db.get_book_files(book_id, 'audio')
    part_label = "E-kitob" if file_type == 'document' else "Audio"
    await message.answer(
        f"✅ {part_label} qismi qo'shildi!\n\n"
        f"📄 E-kitob qismlari: {len(doc_parts)} ta\n"
        f"🎧 Audio qismlari: {len(audio_parts)} ta\n\n"
        "Yana fayl yuborishingiz yoki \"Yakunlash\" tugmasini bosishingiz mumkin."
    )

@router.callback_query(F.data == "finish_multi_part_book")
async def finish_multi_part_book_callback(callback: CallbackQuery, state: FSMContext):
    """Qismli kitobni yakunlash"""
    data = await state.get_data()
    book_id = data.get('book_id')
    if not book_id:
        await callback.answer("Hali hech bo'lmaganda bitta fayl yuboring.", show_alert=True)
        return
    book = db.get_book_by_id(book_id)
    if not book:
        await callback.answer("Kitob topilmadi.", show_alert=True)
        await state.clear()
        return
    doc_count = len(db.get_book_files(book_id, 'document'))
    audio_count = len(db.get_book_files(book_id, 'audio'))
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Admin panel", callback_data="admin_back")]
    ])
    await callback.message.edit_text(
        f"✅ Qismli kitob saqlandi!\n\n"
        f"📖 {escape_markdown(book['title'])}\n"
        f"📄 E-kitob qismlari: {doc_count} ta\n"
        f"🎧 Audio qismlari: {audio_count} ta",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await state.clear()

async def send_multi_part_choice(bot, chat_id: int, book: dict, reply_to_message_id: int | None = None):
    """Foydalanuvchidan qism turini tanlashni so'rash"""
    doc_count = len(db.get_book_files(book['id'], 'document'))
    audio_count = len(db.get_book_files(book['id'], 'audio'))
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"📄 E-kitob ({doc_count})",
            callback_data=f"send_parts_document_{book['id']}"
        )],
        [InlineKeyboardButton(
            text=f"🎧 Audio ({audio_count})",
            callback_data=f"send_parts_audio_{book['id']}"
        )],
        [InlineKeyboardButton(text="❌ Yopish", callback_data="close_search")]
    ])
    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"🧩 *{escape_markdown(book['title'])}*\n"
            "Fayl turini tanlang:"
        ),
        parse_mode="Markdown",
        reply_markup=keyboard,
        reply_to_message_id=reply_to_message_id  # Guruhlarda reply qilamiz
    )

@router.callback_query(F.data.startswith("send_parts_"))
async def send_book_parts_callback(callback: CallbackQuery):
    """Qismli kitobning ma'lum turdagi fayllarini yuborish"""
    try:
        _, _, part_type, book_id_str = callback.data.split("_", 3)
    except ValueError:
        await callback.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)
        return
    file_type = 'document' if part_type == 'document' else 'audio'
    try:
        book_id = int(book_id_str)
    except ValueError:
        await callback.answer("❌ Noto'g'ri kitob ID si.", show_alert=True)
        return
    book = db.get_book_by_id(book_id)
    if not book:
        await callback.answer("❌ Kitob topilmadi.", show_alert=True)
        return
    files = db.get_book_files(book_id, file_type)
    if not files:
        await callback.answer("❌ Bu formatdagi fayl mavjud emas.", show_alert=True)
        return
    icon = "📄" if file_type == 'document' else "🎧"
    await callback.answer()
    
    # Xabar yuborishni boshlash
    status_msg = await callback.message.answer(
        f"⏳ {icon} *{escape_markdown(book['title'])}*\n"
        f"Fayllar yuborilmoqda: 0/{len(files)}",
        parse_mode="Markdown"
    )

    sent_count = 0
    for idx, file in enumerate(files, 1):
        caption = (
            f"{icon} *{escape_markdown(book['title'])}*\n"
            f"Qism {idx}/{len(files)}\n"
            f"💾 Hajmi: {format_file_size(file['file_size'] or 0)}"
        )
        from_chat = file.get('storage_chat_id') or book.get('storage_chat_id') or config.STORAGE_CHANNEL_ID
        storage_message_id = file.get('storage_message_id')
        
        # Har bir fayl uchun retry logikasi
        max_retries = 5
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                if storage_message_id and from_chat:
                    try:
                        await callback.bot.copy_message(
                            chat_id=callback.message.chat.id,
                            from_chat_id=from_chat,
                            message_id=storage_message_id,
                            caption=caption,
                            parse_mode="Markdown"
                        )
                    except Exception as copy_error:
                        # Agar copy_message ishlamasa, file_id orqali yuboramiz
                        # print(f"DEBUG: copy_message xatolik, file_id orqali yuborilmoqda: {copy_error}")
                        if file_type == 'document':
                            await callback.bot.send_document(
                                chat_id=callback.message.chat.id,
                                document=file['file_id'],
                                caption=caption,
                                parse_mode="Markdown"
                            )
                        else:
                            await callback.bot.send_audio(
                                chat_id=callback.message.chat.id,
                                audio=file['file_id'],
                                caption=caption,
                                parse_mode="Markdown"
                            )
                else:
                    if file_type == 'document':
                        await callback.bot.send_document(
                            chat_id=callback.message.chat.id,
                            document=file['file_id'],
                            caption=caption,
                            parse_mode="Markdown"
                        )
                    else:
                        await callback.bot.send_audio(
                            chat_id=callback.message.chat.id,
                            audio=file['file_id'],
                            caption=caption,
                            parse_mode="Markdown"
                        )
                
                # Muvaffaqiyatli yuborildi
                sent_count += 1
                
                # Har 5 ta fayldan keyin statusni yangilaymiz
                if sent_count % 5 == 0:
                    try:
                        await status_msg.edit_text(
                            f"⏳ {icon} *{escape_markdown(book['title'])}*\n"
                            f"Fayllar yuborilmoqda: {sent_count}/{len(files)}",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
                
                # Muvaffaqiyatli yuborilgandan keyin tsikldan chiqamiz
                # Biroz kutish flood control oldini olish uchun
                await asyncio.sleep(0.5) 
                break
                
            except TelegramRetryAfter as e:
                wait_time = e.retry_after
                # print(f"DEBUG: Flood control, {wait_time} soniya kutilmoqda...")
                if retry_count == 0: # Faqat birinchi marta xabar beramiz
                     try:
                        await status_msg.edit_text(
                            f"⏳ Telegram limitiga duch keldik. {wait_time} soniya kutilmoqda...\n"
                            f"Fayllar yuborilmoqda: {sent_count}/{len(files)}"
                        )
                     except:
                        pass
                
                await asyncio.sleep(wait_time + 1)
                retry_count += 1
                continue
                
            except Exception as e:
                error_str = str(e).lower()
                if "flood control" in error_str or "retry after" in error_str:
                     match = re.search(r'retry after (\d+)', error_str, re.IGNORECASE)
                     wait_time = int(match.group(1)) if match else 10
                     
                     if retry_count == 0:
                         try:
                            await status_msg.edit_text(
                                f"⏳ Telegram limitiga duch keldik. {wait_time} soniya kutilmoqda...\n"
                                f"Fayllar yuborilmoqda: {sent_count}/{len(files)}"
                            )
                         except:
                            pass
                     
                     await asyncio.sleep(wait_time + 1)
                     retry_count += 1
                     continue
                
                if "not enough rights" in error_str or "can't send" in error_str or "permission" in error_str:
                    await callback.message.answer("❌ Botda guruhda hujjat yuborish huquqi yo'q. Botni admin qiling!")
                    return
                
                # Boshqa xatolik bo'lsa
                print(f"ERROR processing file {idx}: {e}")
                # Bitta fayl xato bersa ham keyingisiga o'tamiz (lekin xabar chiqaramiz)
                await callback.message.answer(f"❌ {idx}-qismni yuborishda xatolik: {e}")
                break

    # Yakuniy xabar
    try:
        await status_msg.delete()
    except:
        pass
        
    await callback.message.answer(
        f"✅ *{escape_markdown(book['title'])}*\n"
        f"Barcha fayllar yuborildi ({sent_count}/{len(files)} ta)!",
        parse_mode="Markdown"
    )
@router.message(BookStates.multi_part_title)
async def process_multi_part_title(message: Message, state: FSMContext):
    """Qismli kitob nomini qabul qilish"""
    title = (message.text or "").strip()
    if len(title) < 2:
        await message.answer("❌ Kitob nomi kamida 2 ta belgidan iborat bo'lishi kerak.")
        return
    await state.update_data(multi_title=title, book_id=None)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yakunlash", callback_data="finish_multi_part_book")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")]
    ])
    await message.answer(
        "📤 Endi kitobning qismlarini yuboring.\n\n"
        "• E-kitob: PDF, DOCX, XLSX va boshqa hujjat fayllari.\n"
        "• Audio: MP3, WAV, OGG, M4A va boshqa treklar.\n\n"
        "Har bir fayl yuborilgandan so'ng avtomatik saqlanadi.\n"
        "✅ Tugatgach \"Yakunlash\" tugmasini bosing.",
        reply_markup=keyboard
    )
    await state.set_state(BookStates.multi_part_collecting)
