"""
Asosiy handlerlar
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import Database
from utils.helpers import is_admin, escape_markdown, format_file_size
from utils.subscription import is_subscribed_to_all, check_subscription, get_subscription_message_async
import config

router = Router()
# Guruhlarda ham ishlashi uchun filter olib tashlandi
db = Database()

async def safe_reply_or_send(message: Message, text: str, reply_markup=None, parse_mode=None):
    """Guruhlarda xavfsiz javob berish funksiyasi"""
    if message.chat.type in ["group", "supergroup"]:
        try:
            await message.reply(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            # Agar reply ishlamasa, oddiy send_message ishlatamiz
            await message.bot.send_message(
                chat_id=message.chat.id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
    else:
        await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)

class AdminStates(StatesGroup):
    pass  # Admin states endi admin.py da

@router.message(Command("start"))
async def start_handler(message: Message):
    """Start buyrug'i"""
    print(f"DEBUG: /start buyrug'i qabul qilindi - chat_id={message.chat.id}, chat_type={message.chat.type}, user_id={message.from_user.id}")
    user = message.from_user
    chat = message.chat
    
    # Foydalanuvchini ma'lumotlar bazasiga qo'shish
    db.add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        is_bot=user.is_bot,
        language_code=user.language_code
    )
    
    # Agar guruh bo'lsa, guruhni ham qo'shish
    if chat.type in ["group", "supergroup"]:
        db.add_group(
            group_id=chat.id,
            title=chat.title or "Noma'lum",
            group_type=chat.type
        )
    
    # Majburiy obuna tekshirish
    if not await is_subscribed_to_all(message.bot, user.id):
        print(f"DEBUG: Majburiy obuna tekshiruvi - obuna bo'lmagan")
        msg_text, keyboard = await get_subscription_message_async(message.bot)
        await safe_reply_or_send(message, msg_text, reply_markup=keyboard)
        return
    
    welcome_text = f"""
👋 Salom, {user.first_name}!

📚 Bu bot orqali siz kitoblar qidirishingiz mumkin.

🔍 Kitob qidirish uchun faqat kitob nomini yozing.

📖 Botda mavjud bo'lgan kitoblar:
• PDF kitoblar
• Audio kitoblar

Qidirishni boshlang! 🔍
"""
    
    print(f"DEBUG: Welcome xabar yuborilmoqda")
    await safe_reply_or_send(message, welcome_text)
    print(f"DEBUG: Welcome xabar yuborildi")

@router.message(Command("stop"))
async def stop_handler(message: Message, state: FSMContext):
    """Avtomatik yuklashni to'xtatish"""
    # Admin buyruqlari faqat shaxsiy chatda ishlaydi
    if message.chat.type != "private":
        return
    
    if not is_admin(message.from_user.id):
        await message.answer("❌ Sizda admin huquqi yo'q!")
        return
    
    from handlers.books import BookStates
    current_state = await state.get_state()
    if current_state == BookStates.auto_upload_mode:
        await state.clear()
        await message.answer("✅ Avtomatik kitob qo'shish to'xtatildi!")
    elif current_state in [BookStates.multi_part_title, BookStates.multi_part_collecting]:
        await state.clear()
        await message.answer("✅ Qismli kitob qo'shish rejimi to'xtatildi!")
    else:
        await message.answer("ℹ️ Avtomatik yuklash rejimi faol emas.")

@router.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: CallbackQuery):
    """Obuna holatini tekshirish"""
    user_id = callback.from_user.id
    
    # Obuna holatini tekshirish
    subscribed = await is_subscribed_to_all(callback.bot, user_id)
    
    if subscribed:
        # Barcha kanallarga obuna bo'lgan
        await callback.message.edit_text(
            "✅ Barcha kanallarga obuna bo'lgansiz!\n\n"
            "Endi botdan foydalanishingiz mumkin. /start buyrug'ini bosing yoki kitob qidiring."
        )
        
        # Welcome xabar yuborish
        user = callback.from_user
        welcome_text = f"""
👋 Salom, {user.first_name}!

📚 Bu bot orqali siz kitoblar qidirishingiz mumkin.

🔍 Kitob qidirish uchun faqat kitob nomini yozing.

📖 Botda mavjud bo'lgan kitoblar:
• PDF kitoblar
• Audio kitoblar

Qidirishni boshlang! 🔍
"""
        await callback.message.answer(welcome_text)
    else:
        # Hali barcha kanallarga obuna bo'lmagan
        from database.db import Database
        db = Database()
        required_channels = db.get_required_channels()
        subscription_status = await check_subscription(callback.bot, user_id)
        
        not_subscribed = []
        for channel in required_channels:
            channel_id = channel['channel_id']
            if not subscription_status.get(channel_id, False):
                channel_title = channel['channel_title'] or channel['channel_username'] or channel['channel_id']
                not_subscribed.append(channel_title)
        
        await callback.answer(
            f"❌ Hali quyidagi kanallarga obuna bo'lmadingiz:\n" + 
            "\n".join([f"• {ch}" for ch in not_subscribed]),
            show_alert=True
        )

@router.message(Command("help"))
async def help_handler(message: Message):
    """Yordam buyrug'i"""
    help_text = """
📖 Bot haqida ma'lumot:

🔍 **Kitob qidirish:**
Faqat kitob nomini yozing va bot sizga mos keladigan kitoblarni topib beradi.

📚 **Qo'llab-quvvatlanadigan formatlar:**
• PDF fayllar
• Audio fayllar (MP3, WAV, OGG, M4A, FLAC)

📞 **Aloqa:**
Savollar bo'lsa admin bilan bog'laning.
"""
    
    await safe_reply_or_send(message, help_text, parse_mode="Markdown")

@router.message(Command("admin"))
async def admin_handler(message: Message):
    """Admin panel (faqat shaxsiy chatda ishlaydi)"""
    # Admin panel faqat shaxsiy chatda ishlaydi
    if message.chat.type != "private":
        await safe_reply_or_send(message, "❌ Admin panel faqat shaxsiy chatda ishlaydi. Botga shaxsiy xabar yuboring.")
        return
    
    if not is_admin(message.from_user.id):
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📚 Kitoblar ro'yxati", callback_data="admin_books")],
        [InlineKeyboardButton(text="➕ Kitob qo'shish", callback_data="admin_add_book")],
        [InlineKeyboardButton(text="🗑 Kitob o'chirish", callback_data="admin_delete_book")],
        [InlineKeyboardButton(text="📢 Kanal qo'shish", callback_data="admin_add_channel")],
        [InlineKeyboardButton(text="📋 Kanallar ro'yxati", callback_data="admin_channels")],
        [InlineKeyboardButton(text="📢 Reklama tarqatish", callback_data="admin_broadcast")]
    ])
    
    await message.answer("👨‍💼 Admin panel:", reply_markup=keyboard)

@router.callback_query(F.data == "admin_stats")
async def admin_stats_callback(callback: CallbackQuery):
    """Statistika ko'rsatish"""
    stats = db.get_statistics()
    
    stats_text = f"""
📊 **Bot statistikasi:**

📚 Kitoblar soni: {stats['books_count']}
👥 Foydalanuvchilar soni: {stats['users_count']}
👥 Guruhlar soni: {stats['groups_count']}
📢 Majburiy obuna kanallari: {stats['channels_count']}
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(stats_text, reply_markup=keyboard)

@router.callback_query(F.data == "admin_books")
async def admin_books_callback(callback: CallbackQuery):
    """Kitoblar ro'yxatini ko'rsatish"""
    books = db.get_all_books()
    
    if not books:
        await callback.message.edit_text("📚 Hozircha kitoblar mavjud emas.")
        return
    
    books_text = "📚 **Kitoblar ro'yxati:**\n\n"
    
    for book in books[:10]:  # Faqat birinchi 10 ta kitobni ko'rsatish
        title = escape_markdown(book['title'])
        author = escape_markdown(book['author'] or "Noma'lum")
        file_size = format_file_size(book['file_size'])
        
        books_text += f"📖 **{title}**\n"
        books_text += f"👤 Muallif: {author}\n"
        if book.get('is_multi_part'):
            doc_parts = len(db.get_book_files(book['id'], 'document'))
            audio_parts = len(db.get_book_files(book['id'], 'audio'))
            books_text += f"📁 Turi: 🧩 Qismli (📄 {doc_parts} / 🎧 {audio_parts})\n"
        else:
            books_text += f"📁 Turi: {book['file_type']}\n"
            books_text += f"💾 Hajmi: {file_size}\n"
            books_text += f"🆔 ID: `{book['id']}`\n\n"
    
    if len(books) > 10:
        books_text += f"... va yana {len(books) - 10} ta kitob"
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")]
    ])
        
    await callback.message.edit_text(books_text, parse_mode="Markdown", reply_markup=keyboard)

@router.callback_query(F.data == "admin_add_book")
async def admin_add_book_callback(callback: CallbackQuery, state: FSMContext):
    """Kitob qo'shish"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Bitta kitob qo'shish", callback_data="add_single_book")],
        [InlineKeyboardButton(text="📚📚 Ko'p kitob qo'shish (Avtomatik)", callback_data="add_multiple_books")],
        [InlineKeyboardButton(text="🧩 Qismli kitob qo'shish", callback_data="add_multi_part_book")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")]
    ])
    await callback.message.edit_text("📚 Kitob qo'shish usulini tanlang:", reply_markup=keyboard)

@router.callback_query(F.data == "add_single_book")
async def add_single_book_callback(callback: CallbackQuery, state: FSMContext):
    """Bitta kitob qo'shish"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")]
    ])
    await callback.message.edit_text("📚 Kitob qo'shish uchun faylni yuklang.", reply_markup=keyboard)
    await state.clear()  # State ni tozalash

@router.callback_query(F.data == "add_multiple_books")
async def add_multiple_books_callback(callback: CallbackQuery, state: FSMContext):
    """Ko'p kitob qo'shish (avtomatik)"""
    await callback.message.edit_text("📚📚 **Avtomatik kitob qo'shish rejimi faollashtirildi!**\n\n"
                                   "Endi fayllarni yuklang. Bot avtomatik ravishda:\n"
                                   "• Fayl nomidan kitob nomini aniqlaydi\n"
                                   "• Muallifni aniqlaydi\n"
                                   "• Kitobni ma'lumotlar bazasiga qo'shadi\n\n"
                                   "**To'xtatish uchun** /stop buyrug'ini yuboring yoki tugmani bosing.",
                                   reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                       [InlineKeyboardButton(text="⏹️ To'xtatish", callback_data="stop_auto_upload")],
                                       [InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")]
                                   ]))
    # books.py faylida BookStates.auto_upload_mode ni ishlatish kerak
    from handlers.books import BookStates
    await state.set_state(BookStates.auto_upload_mode)

@router.callback_query(F.data == "stop_auto_upload")
async def stop_auto_upload_callback(callback: CallbackQuery, state: FSMContext):
    """Avtomatik yuklashni to'xtatish"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")]
    ])
    await callback.message.edit_text("✅ Avtomatik kitob qo'shish to'xtatildi!", reply_markup=keyboard)
    await state.clear()

@router.callback_query(F.data.startswith("channel_info_"))
async def channel_info_callback(callback: CallbackQuery):
    """URL yo'q bo'lgan private kanal tugmasi bosilganda foydalanuvchiga haqiqiy invite link yaratib berish."""
    channel_id = callback.data.split("channel_info_")[-1]
    try:
        # Avval mavjud invite linkni eksport qilishga urinamiz
        invite_link = None
        try:
            chat = await callback.bot.get_chat(channel_id)
            try:
                invite_link = await callback.bot.export_chat_invite_link(chat.id)
            except Exception:
                # Yangi muddatsiz taklif havolasini yaratish
                new_invite = await callback.bot.create_chat_invite_link(chat.id)
                invite_link = getattr(new_invite, 'invite_link', None)
        except Exception:
            invite_link = None

        if invite_link and isinstance(invite_link, str) and invite_link.startswith("http"):
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Kanalga o'tish ▶️", url=invite_link)],
                                                       [InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_subscription")]])
            await callback.message.answer("Kanalga o'tish uchun tugmani bosing:", reply_markup=kb)
        else:
            await callback.answer("Havola olinmadi. Admin botga invite yaratish ruxsatini bersin.", show_alert=True)
    except Exception as e:
        await callback.answer("Xatolik yuz berdi.", show_alert=True)

@router.callback_query(F.data == "admin_back")
async def admin_back_callback(callback: CallbackQuery, state: FSMContext):
    """Admin panelga qaytish"""
    await state.clear()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📚 Kitoblar ro'yxati", callback_data="admin_books")],
        [InlineKeyboardButton(text="➕ Kitob qo'shish", callback_data="admin_add_book")],
        [InlineKeyboardButton(text="🗑 Kitob o'chirish", callback_data="admin_delete_book")],
        [InlineKeyboardButton(text="📢 Kanal qo'shish", callback_data="admin_add_channel")],
        [InlineKeyboardButton(text="📋 Kanallar ro'yxati", callback_data="admin_channels")],
        [InlineKeyboardButton(text="📢 Reklama tarqatish", callback_data="admin_broadcast")]
    ])
    await callback.message.edit_text("👨‍💼 Admin panel:", reply_markup=keyboard)

def _format_admin_book_entry(book, index: int) -> str:
    title = escape_markdown(book['title'])
    author = escape_markdown(book['author'] or "Noma'lum")
    text = f"{index}. **{title}**"
    if book.get('is_multi_part'):
        doc_parts = len(db.get_book_files(book['id'], 'document'))
        audio_parts = len(db.get_book_files(book['id'], 'audio'))
        text += " 🧩\n"
        text += f"   📄 {doc_parts} ta | 🎧 {audio_parts} ta\n"
    else:
        text += "\n"
        text += f"   📁 {book['file_type']} | {format_file_size(book['file_size'])}\n"
    text += f"   👤 {author}\n"
    text += f"   🆔 `{book['id']}`\n"
    return text

async def _show_admin_delete_list(callback: CallbackQuery, books: list, page: int = 0):
    items_per_page = 10
    total_pages = (len(books) + items_per_page - 1) // items_per_page
    page = max(0, min(page, total_pages - 1 if total_pages else 0))
    start_idx = page * items_per_page
    page_books = books[start_idx:start_idx + items_per_page]
    
    text = "🗑 **O'chirish kerak bo'lgan kitobni tanlang:**\n\n"
    for i, book in enumerate(page_books, 1):
        text += _format_admin_book_entry(book, start_idx + i)
        text += "\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    row = []
    for i, book in enumerate(page_books, 1):
        global_idx = start_idx + i
        row.append(InlineKeyboardButton(
            text=str(global_idx),
            callback_data=f"delete_book_{book['id']}_{page}"
        ))
        if len(row) == 5:
            keyboard.inline_keyboard.append(row)
            row = []
    if row:
        keyboard.inline_keyboard.append(row)
    
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_delete_page_{page-1}"))
    nav_row.append(InlineKeyboardButton(text="🔙", callback_data="admin_back"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_delete_page_{page+1}"))
    keyboard.inline_keyboard.append(nav_row)
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)

@router.callback_query(F.data == "admin_delete_book")
async def admin_delete_book_callback(callback: CallbackQuery):
    """Kitob o'chirish"""
    books = db.get_all_books()
    
    if not books:
        await callback.message.edit_text("📚 O'chirish uchun kitoblar mavjud emas.", reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")]]
        ))
        return
    
    await _show_admin_delete_list(callback, books, page=0)

@router.callback_query(F.data.startswith("admin_delete_page_"))
async def admin_delete_page_callback(callback: CallbackQuery):
    """Kitob o'chirish sahifalarini almashtirish"""
    try:
        page = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌ Noto'g'ri sahifa.", show_alert=True)
        return
    books = db.get_all_books()
    if not books:
        await callback.message.edit_text("📚 O'chirish uchun kitoblar mavjud emas.", reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")]]
        ))
        return
    await _show_admin_delete_list(callback, books, page=page)

@router.callback_query(F.data.startswith("delete_book_"))
async def delete_book_callback(callback: CallbackQuery):
    """Kitobni o'chirish"""
    parts = callback.data.split("_")
    try:
        book_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0
    except (ValueError, IndexError):
        await callback.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)
        return
    
    if db.delete_book(book_id):
        await callback.answer("✅ Kitob o'chirildi!")
    else:
        await callback.answer("❌ Kitob o'chirishda xatolik.", show_alert=True)
        return
    
    books = db.get_all_books()
    if not books:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")]
        ])
        await callback.message.edit_text("📚 Endi kitoblar mavjud emas.", reply_markup=keyboard)
        return
    total_pages = (len(books) + 9) // 10
    if page >= total_pages:
        page = max(0, total_pages - 1)
    await _show_admin_delete_list(callback, books, page=page)

@router.callback_query(F.data == "admin_add_channel")
async def admin_add_channel_callback(callback: CallbackQuery, state: FSMContext):
    """Kanal qo'shish"""
    from handlers.admin import ChannelStates
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")]
    ])
    await callback.message.edit_text("📢 Majburiy obuna kanalini qo'shish uchun kanal ID, username yoki link yuboring.\n\n"
                                   "Qo'llab-quvvatlanadigan formatlar:\n"
                                   "• @channel_username\n"
                                   "• -1001234567890\n"
                                   "• https://t.me/channel_username\n"
                                   "• https://t.me/c/<internal_id>/<post_id> (private post)\n\n"
                                   "Agar invite link bo'lsa (+XXXX/joinchat), iltimos o'sha kanaldan biror postni botga forward qiling.", reply_markup=keyboard)
    await state.set_state(ChannelStates.waiting_for_channel)

@router.callback_query(F.data == "admin_channels")
async def admin_channels_callback(callback: CallbackQuery):
    """Kanallar ro'yxatini ko'rsatish"""
    channels = db.get_required_channels()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    if not channels:
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")])
        await callback.message.edit_text("📢 Majburiy obuna kanallari mavjud emas.", reply_markup=keyboard)
        return
    
    # Har bir kanal uchun alohida tugma (o'chirish uchun)
    for channel in channels:
        title = channel['channel_title'] or channel['channel_username'] or channel['channel_id']
        button_text = f"🗑 {title}"
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"delete_channel_{channel['id']}"
            )
        ])
    # Orqaga tugmasi
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")])
    await callback.message.edit_text("📢 Majburiy obuna kanallaridan birini o'chirish uchun tanlang:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("delete_channel_"))
async def delete_channel_callback(callback: CallbackQuery):
    """Tanlangan kanalni o'chirish (faolsizlantirish)"""
    try:
        rc_id = int(callback.data.split("_")[2])
    except Exception:
        await callback.answer("Noto'g'ri kanal identifikatori.", show_alert=True)
        return

    if db.delete_required_channel(rc_id):
        # Muvaffaqiyatli o'chirilsa, ro'yxatni yangilaymiz
        channels = db.get_required_channels()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        if not channels:
            keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")])
            await callback.message.edit_text("✅ Kanal o'chirildi. Endi majburiy obuna kanallari yo'q.", reply_markup=keyboard)
            return
        for channel in channels:
            title = channel['channel_title'] or channel['channel_username'] or channel['channel_id']
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"🗑 {title}",
                    callback_data=f"delete_channel_{channel['id']}"
                )
            ])
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")])
        await callback.message.edit_text("✅ Kanal o'chirildi. Qolgan kanallardan birini tanlang:", reply_markup=keyboard)
    else:
        await callback.answer("Kanalni o'chirishda xatolik yuz berdi.", show_alert=True)
