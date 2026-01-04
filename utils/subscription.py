"""
Majburiy obuna tekshirish funksiyalari
"""
from aiogram import Bot
from aiogram.types import ChatMember, InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Optional
from database.db import Database
from utils.helpers import is_admin

async def check_subscription(bot: Bot, user_id: int) -> Dict[str, bool]:
    """Foydalanuvchining majburiy obuna kanallariga obuna ekanligini tekshirish"""
    db = Database()
    required_channels = db.get_required_channels()
    
    subscription_status = {}
    
    for channel in required_channels:
        channel_id = channel['channel_id']
        try:
            member = await bot.get_chat_member(channel_id, user_id)
            subscription_status[channel_id] = member.status in ['member', 'administrator', 'creator']
        except Exception:
            subscription_status[channel_id] = False
    
    return subscription_status

async def is_subscribed_to_all(bot: Bot, user_id: int) -> bool:
    """Foydalanuvchi barcha majburiy kanallarga obuna ekanligini tekshirish"""
    # Adminlar majburiy obunadan mustasno
    if is_admin(user_id):
        return True
    
    db = Database()
    required_channels = db.get_required_channels()
    
    # Agar majburiy obuna kanallari bo'lmasa, foydalanuvchi botdan foydalana oladi
    if not required_channels:
        return True
    
    subscription_status = await check_subscription(bot, user_id)
    return all(subscription_status.values())

async def get_subscription_message_async(bot: Bot) -> tuple[str, Optional[InlineKeyboardMarkup]]:
    """Majburiy obuna haqida xabar matni va inline keyboard (private kanallar uchun linkni dinamik yaratadi)."""
    db = Database()
    required_channels = db.get_required_channels()
    if not required_channels:
        return "Majburiy obuna kanallari mavjud emas.", None

    message = "Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling yoki ariza yuboring 👇"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    for channel in required_channels:
        channel_db_id = channel['id']
        channel_id = channel['channel_id']
        channel_title = channel['channel_title'] or channel['channel_username'] or channel['channel_id']
        invite_link = channel.get('invite_link') if isinstance(channel, dict) else None

        url: Optional[str] = None
        if channel_id.startswith('@'):
            url = f"https://t.me/{channel_id[1:]}"
        elif channel_id.startswith('-100'):
            username = channel.get('channel_username') if isinstance(channel, dict) else None
            if username:
                url = f"https://t.me/{username}"
            elif isinstance(invite_link, str) and invite_link.startswith('http'):
                url = invite_link
            else:
                # Dinamik tarzda invite linkni olish yoki yaratish
                try:
                    chat = await bot.get_chat(channel_id)
                    try:
                        new_link = await bot.export_chat_invite_link(chat.id)
                        url = new_link
                    except Exception:
                        try:
                            created = await bot.create_chat_invite_link(chat.id)
                            url = getattr(created, 'invite_link', None)
                        except Exception:
                            url = None
                    # DB ga saqlash (agar link olinsa)
                    if url:
                        db.update_required_channel_invite_link(channel_db_id, url)
                except Exception:
                    url = None
        # Tugma
        button_text = channel_title[:50] if len(channel_title) > 50 else channel_title
        if url:
            button = InlineKeyboardButton(text=f"{button_text} ▶️", url=url)
        else:
            button = InlineKeyboardButton(text=f"{button_text} ▶️", callback_data=f"channel_info_{channel_id}")
        keyboard.inline_keyboard.append([button])

    keyboard.inline_keyboard.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_subscription")])
    return message, keyboard

def get_subscription_message_text() -> str:
    """Eski funksiya - qayta tuzatish uchun (backward compatibility)"""
    message, _ = get_subscription_message()
    return message
