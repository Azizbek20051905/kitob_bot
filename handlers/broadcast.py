"""
Reklama tarqatish handlerlari
"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import Database
from utils.helpers import is_admin
import asyncio
import logging
from typing import Optional, Dict
from copy import deepcopy

logger = logging.getLogger(__name__)

router = Router()
db = Database()

# Reklama yuborish holatlarini saqlash
broadcast_tasks: Dict[int, Dict] = {}  # {admin_id: {task, status, current, total, paused, message_id}}

class BroadcastStates(StatesGroup):
    waiting_for_message = State()

async def send_message_copy(bot: Bot, chat_id: int, original_message: Message) -> bool:
    """Xabarni nusxalash va yuborish"""
    try:
        if original_message.photo:
            # Rasm bilan xabar
            await bot.send_photo(
                chat_id=chat_id,
                photo=original_message.photo[-1].file_id,
                caption=original_message.caption,
                caption_entities=original_message.caption_entities,
                reply_markup=original_message.reply_markup
            )
        elif original_message.video:
            # Video bilan xabar
            await bot.send_video(
                chat_id=chat_id,
                video=original_message.video.file_id,
                caption=original_message.caption,
                caption_entities=original_message.caption_entities,
                reply_markup=original_message.reply_markup
            )
        elif original_message.document:
            # Hujjat bilan xabar
            await bot.send_document(
                chat_id=chat_id,
                document=original_message.document.file_id,
                caption=original_message.caption,
                caption_entities=original_message.caption_entities,
                reply_markup=original_message.reply_markup
            )
        elif original_message.audio:
            # Audio bilan xabar
            await bot.send_audio(
                chat_id=chat_id,
                audio=original_message.audio.file_id,
                caption=original_message.caption,
                caption_entities=original_message.caption_entities,
                reply_markup=original_message.reply_markup
            )
        elif original_message.voice:
            # Ovoz bilan xabar
            await bot.send_voice(
                chat_id=chat_id,
                voice=original_message.voice.file_id,
                caption=original_message.caption,
                caption_entities=original_message.caption_entities,
                reply_markup=original_message.reply_markup
            )
        elif original_message.video_note:
            # Video note bilan xabar
            await bot.send_video_note(
                chat_id=chat_id,
                video_note=original_message.video_note.file_id,
                reply_markup=original_message.reply_markup
            )
        elif original_message.sticker:
            # Sticker bilan xabar
            await bot.send_sticker(
                chat_id=chat_id,
                sticker=original_message.sticker.file_id,
                reply_markup=original_message.reply_markup
            )
        elif original_message.animation:
            # GIF bilan xabar
            await bot.send_animation(
                chat_id=chat_id,
                animation=original_message.animation.file_id,
                caption=original_message.caption,
                caption_entities=original_message.caption_entities,
                reply_markup=original_message.reply_markup
            )
        else:
            # Oddiy matn xabar
            await bot.send_message(
                chat_id=chat_id,
                text=original_message.text,
                entities=original_message.entities,
                reply_markup=original_message.reply_markup,
                parse_mode=original_message.parse_mode
            )
        return True
    except Exception as e:
        logger.error(f"Xabar yuborishda xatolik (chat_id={chat_id}): {e}")
        return False

async def update_broadcast_status(bot: Bot, admin_id: int, status_msg_id: int, current: int, total: int, paused: bool = False, stopped: bool = False):
    """Reklama yuborish statusini yangilash"""
    try:
        status_text = f"""
📢 **Reklama tarqatish**

📊 **Status:**
{'⏸️ Pauza qilingan' if paused else '⏹️ To\'xtatilgan' if stopped else '📤 Yuborilmoqda...'}

📈 **Progress:**
✅ Jo'natilgan: {current}/{total}
⏳ Qolgan: {total - current}
📊 Foiz: {(current / total * 100) if total > 0 else 0:.1f}%
"""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        
        if not stopped:
            if paused:
                keyboard.inline_keyboard.append([
                    InlineKeyboardButton(text="▶️ Davom ettirish", callback_data="broadcast_resume"),
                    InlineKeyboardButton(text="⏹️ To'xtatish", callback_data="broadcast_stop")
                ])
            else:
                keyboard.inline_keyboard.append([
                    InlineKeyboardButton(text="⏸️ Pauza", callback_data="broadcast_pause"),
                    InlineKeyboardButton(text="⏹️ To'xtatish", callback_data="broadcast_stop")
                ])
        
        await bot.edit_message_text(
            chat_id=admin_id,
            message_id=status_msg_id,
            text=status_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Status yangilashda xatolik: {e}")

async def broadcast_task(bot: Bot, admin_id: int, message: Message, user_ids: list, status_msg_id: int):
    """Reklama yuborish background task"""
    total = len(user_ids)
    current = 0
    failed = 0
    
    broadcast_info = broadcast_tasks.get(admin_id, {})
    broadcast_info['current'] = current
    broadcast_info['total'] = total
    broadcast_info['failed'] = failed
    broadcast_info['paused'] = False
    broadcast_info['stopped'] = False
    broadcast_tasks[admin_id] = broadcast_info
    
    for user_id in user_ids:
        # Pauza yoki to'xtatish tekshiruvi
        if admin_id in broadcast_tasks:
            info = broadcast_tasks[admin_id]
            if info.get('stopped', False):
                await update_broadcast_status(bot, admin_id, status_msg_id, current, total, stopped=True)
                return
            
            # Pauza holatida kutish
            while info.get('paused', False) and not info.get('stopped', False):
                await asyncio.sleep(0.5)
                info = broadcast_tasks.get(admin_id, {})
        
        # Xabarni yuborish
        success = await send_message_copy(bot, user_id, message)
        
        if success:
            current += 1
        else:
            failed += 1
        
        # Status yangilash (har 10 ta yuborilganda yoki oxirida)
        if current % 10 == 0 or current == total:
            if admin_id in broadcast_tasks:
                broadcast_tasks[admin_id]['current'] = current
                broadcast_tasks[admin_id]['failed'] = failed
                await update_broadcast_status(
                    bot, admin_id, status_msg_id, current, total,
                    paused=broadcast_tasks[admin_id].get('paused', False)
                )
        
        # Flood control uchun kichik kechikish
        await asyncio.sleep(0.05)
    
    # Yakuniy status
    if admin_id in broadcast_tasks:
        final_text = f"""
📢 **Reklama tarqatish yakunlandi**

✅ **Natijalar:**
📤 Jo'natilgan: {current}/{total}
❌ Xatolik: {failed}
📊 Muvaffaqiyat: {(current / total * 100) if total > 0 else 0:.1f}%
"""
        try:
            await bot.edit_message_text(
                chat_id=admin_id,
                message_id=status_msg_id,
                text=final_text,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Yakuniy status yangilashda xatolik: {e}")
        
        # Taskni tozalash
        if admin_id in broadcast_tasks:
            del broadcast_tasks[admin_id]

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_callback(callback: CallbackQuery, state: FSMContext):
    """Reklama tarqatish boshlash"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Sizda admin huquqi yo'q!", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(
        "📢 **Reklama tarqatish**\n\n"
        "Reklama xabarini yuboring. Bot barcha foydalanuvchilarga shu xabarni jo'natadi.\n\n"
        "Qo'llab-quvvatlanadigan formatlar:\n"
        "• Matn xabarlar\n"
        "• Rasmli xabarlar\n"
        "• Video xabarlar\n"
        "• Hujjatlar\n"
        "• Audio xabarlar\n"
        "• Tugmali xabarlar (inline keyboard)\n"
        "• Va boshqa barcha xabar turlari",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    
    await state.set_state(BroadcastStates.waiting_for_message)

@router.message(BroadcastStates.waiting_for_message, F.chat.type == "private")
async def process_broadcast_message(message: Message, state: FSMContext, bot: Bot):
    """Reklama xabarini qabul qilish va yuborishni boshlash"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ Sizda admin huquqi yo'q!")
        await state.clear()
        return
    
    # Foydalanuvchilar ro'yxatini olish
    user_ids = db.get_all_user_ids()
    
    if not user_ids:
        await message.answer("❌ Hech qanday foydalanuvchi topilmadi!")
        await state.clear()
        return
    
    # Status xabarini yuborish
    status_text = f"""
📢 **Reklama tarqatish**

📊 **Status:**
🔄 Tayyorlanmoqda...

📈 **Progress:**
✅ Jo'natilgan: 0/{len(user_ids)}
⏳ Qolgan: {len(user_ids)}
📊 Foiz: 0.0%
"""
    
    status_msg = await message.answer(status_text, parse_mode="Markdown")
    status_msg_id = status_msg.message_id
    
    # Background task yaratish
    task = asyncio.create_task(
        broadcast_task(bot, message.from_user.id, message, user_ids, status_msg_id)
    )
    
    # Task ma'lumotlarini saqlash
    broadcast_tasks[message.from_user.id] = {
        'task': task,
        'status_msg_id': status_msg_id,
        'current': 0,
        'total': len(user_ids),
        'paused': False,
        'stopped': False
    }
    
    await state.clear()
    await message.answer("✅ Reklama yuborish boshlandi! Status xabarini kuzatib turing.")

@router.callback_query(F.data == "broadcast_pause")
async def broadcast_pause_callback(callback: CallbackQuery):
    """Reklama yuborishni pauza qilish"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Sizda admin huquqi yo'q!", show_alert=True)
        return
    
    if callback.from_user.id in broadcast_tasks:
        broadcast_tasks[callback.from_user.id]['paused'] = True
        await callback.answer("⏸️ Reklama yuborish pauza qilindi")
        
        # Status yangilash
        info = broadcast_tasks[callback.from_user.id]
        await update_broadcast_status(
            callback.bot,
            callback.from_user.id,
            info['status_msg_id'],
            info['current'],
            info['total'],
            paused=True
        )
    else:
        await callback.answer("❌ Faol reklama yuborish topilmadi!", show_alert=True)

@router.callback_query(F.data == "broadcast_resume")
async def broadcast_resume_callback(callback: CallbackQuery):
    """Reklama yuborishni davom ettirish"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Sizda admin huquqi yo'q!", show_alert=True)
        return
    
    if callback.from_user.id in broadcast_tasks:
        broadcast_tasks[callback.from_user.id]['paused'] = False
        await callback.answer("▶️ Reklama yuborish davom etmoqda")
        
        # Status yangilash
        info = broadcast_tasks[callback.from_user.id]
        await update_broadcast_status(
            callback.bot,
            callback.from_user.id,
            info['status_msg_id'],
            info['current'],
            info['total'],
            paused=False
        )
    else:
        await callback.answer("❌ Faol reklama yuborish topilmadi!", show_alert=True)

@router.callback_query(F.data == "broadcast_stop")
async def broadcast_stop_callback(callback: CallbackQuery):
    """Reklama yuborishni to'xtatish"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Sizda admin huquqi yo'q!", show_alert=True)
        return
    
    if callback.from_user.id in broadcast_tasks:
        broadcast_tasks[callback.from_user.id]['stopped'] = True
        broadcast_tasks[callback.from_user.id]['paused'] = False
        
        # Taskni bekor qilish
        task = broadcast_tasks[callback.from_user.id].get('task')
        if task and not task.done():
            task.cancel()
        
        await callback.answer("⏹️ Reklama yuborish to'xtatildi")
        
        # Status yangilash
        info = broadcast_tasks[callback.from_user.id]
        await update_broadcast_status(
            callback.bot,
            callback.from_user.id,
            info['status_msg_id'],
            info['current'],
            info['total'],
            stopped=True
        )
        
        # Taskni tozalash
        del broadcast_tasks[callback.from_user.id]
    else:
        await callback.answer("❌ Faol reklama yuborish topilmadi!", show_alert=True)

