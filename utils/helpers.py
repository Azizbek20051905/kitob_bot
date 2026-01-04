"""
Yordamchi funksiyalar
"""
import os
import re
from typing import Optional, Tuple
import config

def get_file_type(filename: str) -> Optional[str]:
    """Fayl turini aniqlash"""
    if not filename:
        return None
    
    extension = filename.lower().split('.')[-1]
    
    if extension in config.ALLOWED_FILE_TYPES:
        return config.ALLOWED_FILE_TYPES[extension]
    
    return None

def format_file_size(size_bytes: int) -> str:
    """Fayl hajmini formatlash"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

def clean_filename(filename: str) -> str:
    """Fayl nomini tozalash"""
    # Maxsus belgilarni olib tashlash
    filename = re.sub(r'[^\w\s\-_\.]', '', filename)
    # Bo'shliqlarni pastki chiziq bilan almashtirish
    filename = re.sub(r'\s+', '_', filename)
    return filename.strip()

def extract_book_info(filename: str) -> Tuple[str, str]:
    """Fayl nomidan kitob ma'lumotlarini ajratish"""
    # Fayl kengaytmasini olib tashlash
    name_without_ext = os.path.splitext(filename)[0]
    
    # Fayl nomini tozalash
    name_without_ext = clean_filename(name_without_ext)
    
    # Muallif va kitob nomini ajratish (turli formatlar)
    patterns = [
        r'^(.+?)\s*-\s*(.+)$',  # "Muallif - Kitob nomi"
        r'^(.+?)\s*_\s*(.+)$',  # "Muallif _ Kitob nomi"
        r'^(.+?)\s*by\s*(.+)$', # "Kitob nomi by Muallif"
        r'^(.+?)\s*\((.+?)\)$', # "Kitob nomi (Muallif)"
        r'^(.+?)\s*\[(.+?)\]$', # "Kitob nomi [Muallif]"
    ]
    
    for pattern in patterns:
        match = re.match(pattern, name_without_ext, re.IGNORECASE)
        if match:
            if 'by' in pattern:
                # "Kitob nomi by Muallif" formatida
                title = match.group(1).strip()
                author = match.group(2).strip()
            elif '(' in pattern or '[' in pattern:
                # "Kitob nomi (Muallif)" yoki "Kitob nomi [Muallif]" formatida
                title = match.group(1).strip()
                author = match.group(2).strip()
            else:
                # "Muallif - Kitob nomi" formatida
                author = match.group(1).strip()
                title = match.group(2).strip()
            
            # Bo'sh bo'lmagan va juda qisqa bo'lmagan ma'lumotlarni qaytarish
            if len(title) > 2 and len(author) > 2:
                return title, author
    
    # Agar pattern topilmasa, butun nomni kitob nomi sifatida qaytarish
    if len(name_without_ext) > 2:
        return name_without_ext.strip(), "Noma'lum muallif"
    else:
        return "Noma'lum kitob", "Noma'lum muallif"

def is_admin(user_id: int) -> bool:
    """Foydalanuvchi admin ekanligini tekshirish"""
    return user_id == config.ADMIN_ID

def validate_file_size(file_size: int) -> bool:
    """Fayl hajmini tekshirish"""
    max_size_bytes = config.MAX_FILE_SIZE * 1024 * 1024  # MB dan byte ga
    return file_size <= max_size_bytes

def escape_markdown(text: str) -> str:
    """Markdown belgilarini escape qilish"""
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text
