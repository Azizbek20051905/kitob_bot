"""
Admin kanal qo'shish handleri
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import Database
from utils.helpers import is_admin, escape_markdown
import config

router = Router()
db = Database()

class ChannelStates(StatesGroup):
    waiting_for_channel = State()

@router.message(ChannelStates.waiting_for_channel, F.forward_from_chat)
async def process_channel_forward(message: Message, state: FSMContext):
    """Private kanal(post) forwardi orqali kanalni aniqlash"""
    # Admin buyruqlari faqat shaxsiy chatda ishlaydi
    if message.chat.type != "private":
        await state.clear()
        return
    
    if not is_admin(message.from_user.id):
        await message.answer("❌ Sizda admin huquqi yo'q!")
        await state.clear()
        return
    try:
        chat = message.forward_from_chat
        if not chat:
            await message.answer("❌ Forward xabar orqali kanal aniqlanmadi. Iltimos, kanal postini forward qiling.")
            return
        channel_id = str(chat.id)
        channel_title = chat.title
        channel_username = getattr(chat, 'username', None)
        # Forward orqali ham invite link yaratishga urinamiz
        invite_link = None
        try:
            invite_link = await message.bot.export_chat_invite_link(chat.id)
        except Exception:
            invite_link = None
            # Fallback: yangi taklif havolasini yaratish (muddatsiz)
            try:
                new_invite = await message.bot.create_chat_invite_link(chat.id)
                invite_link = getattr(new_invite, 'invite_link', None)
            except Exception:
                invite_link = None

        db.add_required_channel(
            channel_id=channel_id,
            channel_title=channel_title,
            channel_username=channel_username,
            invite_link=invite_link
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")]])
        username_str = channel_username or "Noma'lum"
        await message.answer(
            f"✅ Kanal qo'shildi!\n\n📢 {channel_title}\n🆔 ID: {channel_id}\n👤 Username: @{username_str}",
            reply_markup=keyboard
        )
    except Exception as e:
        await message.answer(f"❌ Xatolik: {str(e)}")
    finally:
        await state.clear()

@router.message(ChannelStates.waiting_for_channel)
async def process_channel(message: Message, state: FSMContext):
    """Kanal ma'lumotlarini qabul qilish"""
    # Admin buyruqlari faqat shaxsiy chatda ishlaydi
    if message.chat.type != "private":
        await state.clear()
        return
    
    if not is_admin(message.from_user.id):
        await message.answer("❌ Sizda admin huquqi yo'q!")
        await state.clear()
        return
    
    # Matn xabarni tekshirish
    if not message.text:
        await message.answer("❌ Kanal ID, username yoki link kiriting!")
        return
    
    channel_input = message.text.strip()
    
    if not channel_input:
        await message.answer("❌ Kanal ID, username yoki link kiriting!")
        return
    
    try:
        # Kanal ID ni aniqlash
        channel_id = None
        channel_username = None
        
        # Telegram link formatini tekshirish
        if channel_input.startswith('https://t.me/') or channel_input.startswith('http://t.me/'):
            # 1) Maxfiy kanal post linki: https://t.me/c/<internal_id>/<post_id>
            #    Bu holda chat_id = -100<internal_id>
            # 2) Ochiq kanal: https://t.me/<username>
            # 3) Invite linklar: https://t.me/+XXXX yoki https://t.me/joinchat/XXXX (bunda botni kanalga qo'shish talab qilinadi)
            link_path = channel_input.replace('https://t.me/', '').replace('http://t.me/', '')
            parts = link_path.strip('/').split('/')
            if len(parts) >= 2 and parts[0] == 'c' and parts[1].isdigit():
                internal_id = parts[1]
                channel_id = f"-100{internal_id}"
                channel_username = None
            elif len(parts) >= 1 and parts[0].startswith('+'):
                # Invite link: +XXXX – chat_id ni aniqlab bo'lmaydi
                channel_id = None
                channel_username = None
            elif len(parts) >= 1 and parts[0] in ('joinchat',):
                # joinchat/XXXX – chat_id ni aniqlab bo'lmaydi
                channel_id = None
                channel_username = None
            else:
                # Ochiq kanal username
                username_part = parts[0].replace('@', '') if parts else ''
                if username_part:
                    channel_username = username_part
                    channel_id = f"@{username_part}"
        elif channel_input.startswith('@'):
            # Username orqali: @channel_username
            channel_username = channel_input[1:]
            channel_id = channel_input
        elif channel_input.startswith('-100'):
            # ID orqali: -1001234567890
            channel_id = channel_input
            channel_username = None
        elif channel_input.isdigit() or (channel_input.startswith('-') and channel_input[1:].isdigit()):
            # Faqat raqamlar: 1234567890 yoki -1234567890
            channel_id = channel_input
            channel_username = None
        else:
            await message.answer("❌ Noto'g'ri format! Kanal ID, @username yoki link kiriting.\n\n"
                               "Misol:\n"
                               "• @channel_username\n"
                               "• -1001234567890\n"
                               "• https://t.me/channel_username")
            return
        
        # Kanal ma'lumotlarini olish (faqat chat_id yoki @username mavjud bo'lsa)
        channel_title = None
        if channel_id:
            try:
                chat = await message.bot.get_chat(channel_id)
                channel_title = chat.title
                # Agar username o'zgardi yoki yangi bo'lsa, chat dan olish
                if not channel_username and getattr(chat, 'username', None):
                    channel_username = chat.username
                # Private kanal bo'lsa, invite linkni olishga harakat qilamiz
                invite_link = None
                try:
                    invite_link = await message.bot.export_chat_invite_link(chat.id)
                except Exception:
                    invite_link = None
                    try:
                        new_invite = await message.bot.create_chat_invite_link(chat.id)
                        invite_link = getattr(new_invite, 'invite_link', None)
                    except Exception:
                        invite_link = None
            except Exception as e:
                error_msg = str(e)
                if "chat not found" in error_msg.lower() or "not found" in error_msg.lower():
                    await message.answer("❌ Kanal topilmadi. Kanal username yoki ID sini tekshiring.")
                elif "not enough rights" in error_msg.lower() or "admin" in error_msg.lower():
                    await message.answer("❌ Botda kanalga yetarli huquq yo'q. Botni kanalga qo'shib, admin qiling va yana urinib ko'ring.")
                else:
                    await message.answer(f"❌ Xatolik: {error_msg}\n\nKanal ID yoki username ni tekshiring.")
                return
        else:
            # Invite link bo'lsa, adminni yo'naltiramiz
            await message.answer(
                "ℹ️ Bu maxfiy kanal havolasi (invite link). Iltimos, botni o'sha kanalga qo'shib admin qiling va \n"
                "kanal ID sini (-100 bilan boshlanadi) yuboring yoki kanal post havolasidan (t.me/c/<id>/<post>) foydalaning."
            )
            return
        
        # Kanalni ma'lumotlar bazasiga qo'shish
        db.add_required_channel(
            channel_id=channel_id,
            channel_title=channel_title,
            channel_username=channel_username,
            invite_link=invite_link
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")]
        ])
        
        # Xabarni formatlash (parse_mode siz, xavfsiz)
        title = str(channel_title or "Noma'lum")
        channel_id_str = str(channel_id or "Noma'lum")
        username_str = channel_username or 'Noma\'lum'
        invite_link_str = invite_link or 'yo\'q'
        
        response_text = (
            f"✅ Kanal muvaffaqiyatli qo'shildi!\n\n"
            f"📢 {title}\n"
            f"🆔 ID: {channel_id_str}\n"
            f"👤 Username: @{username_str}\n"
            f"🔗 Invite: {invite_link_str}"
        )
        
        await message.answer(response_text, reply_markup=keyboard)
        
    except Exception as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")]
        ])
        await message.answer(f"❌ Kanal qo'shishda xatolik: {str(e)}", reply_markup=keyboard)
    
    await state.clear()
    