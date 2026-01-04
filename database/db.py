"""
Ma'lumotlar bazasi modellari va funksiyalari
"""
import sqlite3
import json
from typing import List, Dict, Optional
from datetime import datetime
import config

class Database:
    def __init__(self):
        self.db_path = config.DATABASE_PATH
        self.init_database()
    
    def init_database(self):
        """Ma'lumotlar bazasini yaratish va jadvallarni tayyorlash"""
        import os
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Kitoblar jadvali
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT,
                file_id TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_size INTEGER,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                uploader_id INTEGER,
                description TEXT,
                storage_message_id INTEGER,
                storage_chat_id TEXT,
                is_multi_part BOOLEAN DEFAULT FALSE
            )
        ''')

        # Qo'shimcha ustunlar mavjudligini tekshirish va qo'shish (migratsiya)
        cursor.execute("PRAGMA table_info(books)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        if 'storage_message_id' not in existing_cols:
            cursor.execute("ALTER TABLE books ADD COLUMN storage_message_id INTEGER")
        if 'storage_chat_id' not in existing_cols:
            cursor.execute("ALTER TABLE books ADD COLUMN storage_chat_id TEXT")
        if 'is_multi_part' not in existing_cols:
            cursor.execute("ALTER TABLE books ADD COLUMN is_multi_part BOOLEAN DEFAULT FALSE")
        # Kitob fayllari jadvali (qismlar)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS book_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                file_id TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_size INTEGER,
                storage_message_id INTEGER,
                storage_chat_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE
            )
        ''')

        
        # Foydalanuvchilar jadvali
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_bot BOOLEAN DEFAULT FALSE,
                language_code TEXT,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Guruhlar jadvali
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY,
                title TEXT,
                type TEXT,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        ''')
        # Guruhlar jadvali uchun migratsiya: last_activity ustunini qo'shish
        cursor.execute("PRAGMA table_info(groups)")
        groups_existing_cols = {row[1] for row in cursor.fetchall()}
        if 'last_activity' not in groups_existing_cols:
            cursor.execute("ALTER TABLE groups ADD COLUMN last_activity TIMESTAMP")
        
        # Majburiy obuna kanallari
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS required_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT UNIQUE NOT NULL,
                channel_title TEXT,
                channel_username TEXT,
                invite_link TEXT,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        ''')
        # Qo'shimcha ustunlarni migratsiya tarzida qo'shish
        cursor.execute("PRAGMA table_info(required_channels)")
        rc_existing_cols = {row[1] for row in cursor.fetchall()}
        if 'invite_link' not in rc_existing_cols:
            cursor.execute("ALTER TABLE required_channels ADD COLUMN invite_link TEXT")
        
        # Eski kitoblar uchun book_files jadvalini to'ldirish
        cursor.execute('SELECT id, file_id, file_type, file_size, storage_message_id, storage_chat_id FROM books')
        books_rows = cursor.fetchall()
        for row in books_rows:
            cursor.execute('SELECT 1 FROM book_files WHERE book_id = ? LIMIT 1', (row[0],))
            exists = cursor.fetchone()
            if not exists:
                cursor.execute('''
                    INSERT INTO book_files (book_id, file_id, file_type, file_size, storage_message_id, storage_chat_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (row[0], row[1], row[2], row[3], row[4], row[5]))
        
        conn.commit()
        conn.close()
    
    def add_book(self, title: str, author: str, file_id: str, file_type: str, 
                 file_size: int, uploader_id: int, description: str = "",
                 storage_message_id: int | None = None, storage_chat_id: str | None = None,
                 is_multi_part: bool = False) -> int | bool:
        """Yangi kitob qo'shish. Muvaffaqiyatli bo'lsa book_id qaytaradi."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO books (title, author, file_id, file_type, file_size, uploader_id, description, storage_message_id, storage_chat_id, is_multi_part)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (title, author, file_id, file_type, file_size, uploader_id, description, storage_message_id, storage_chat_id, int(is_multi_part)))
            
            book_id = cursor.lastrowid
            conn.commit()
            conn.close()
            # Asosiy faylni book_files jadvaliga qo'shish
            self.add_book_file(
                book_id=book_id,
                file_id=file_id,
                file_type=file_type,
                file_size=file_size,
                storage_message_id=storage_message_id,
                storage_chat_id=storage_chat_id
            )
            return book_id
        except Exception as e:
            print(f"Kitob qo'shishda xatolik: {e}")
            return False
    
    def search_books(self, query: str) -> List[Dict]:
        """Kitob qidirish"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, title, author, file_id, file_type, file_size, upload_date,
                   uploader_id, description, storage_message_id, storage_chat_id,
                    COALESCE(is_multi_part, 0)
            FROM books 
            WHERE title LIKE ? OR author LIKE ? OR description LIKE ?
            ORDER BY title
        ''', (f'%{query}%', f'%{query}%', f'%{query}%'))
        
        books = []
        for row in cursor.fetchall():
            books.append({
                'id': row[0],
                'title': row[1],
                'author': row[2],
                'file_id': row[3],
                'file_type': row[4],
                'file_size': row[5],
                'upload_date': row[6],
                'uploader_id': row[7],
                'description': row[8],
                'storage_message_id': row[9],
                'storage_chat_id': row[10],
                'is_multi_part': bool(row[11])
            })
        
        conn.close()
        return books
    
    def delete_book(self, book_id: int) -> bool:
        """Kitobni o'chirish"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM book_files WHERE book_id = ?', (book_id,))
            cursor.execute('DELETE FROM books WHERE id = ?', (book_id,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Kitob o'chirishda xatolik: {e}")
            return False
    
    def get_all_books(self) -> List[Dict]:
        """Barcha kitoblarni olish"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, title, author, file_id, file_type, file_size, upload_date,
                   uploader_id, description, storage_message_id, storage_chat_id,
                   COALESCE(is_multi_part, 0)
            FROM books
            ORDER BY title
        ''')
        
        books = []
        for row in cursor.fetchall():
            books.append({
                'id': row[0],
                'title': row[1],
                'author': row[2],
                'file_id': row[3],
                'file_type': row[4],
                'file_size': row[5],
                'upload_date': row[6],
                'uploader_id': row[7],
                'description': row[8],
                'storage_message_id': row[9],
                'storage_chat_id': row[10],
                'is_multi_part': bool(row[11])
            })
        
        conn.close()
        return books
    
    def add_user(self, user_id: int, username: str, first_name: str, 
                 last_name: str, is_bot: bool, language_code: str):
        """Foydalanuvchini qo'shish yoki yangilash"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (id, username, first_name, last_name, is_bot, language_code, last_activity)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, username, first_name, last_name, is_bot, language_code))
        
        conn.commit()
        conn.close()
    
    def add_group(self, group_id: int, title: str, group_type: str):
        """Guruhni qo'shish yoki yangilash"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO groups 
            (id, title, type, last_activity)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (group_id, title, group_type))
        
        conn.commit()
        conn.close()
    
    def add_required_channel(self, channel_id: str, channel_title: str, channel_username: str | None, invite_link: str | None = None):
        """Majburiy obuna kanalini qo'shish"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO required_channels 
            (channel_id, channel_title, channel_username, invite_link)
            VALUES (?, ?, ?, ?)
        ''', (channel_id, channel_title, channel_username, invite_link))
        
        conn.commit()
        conn.close()
    
    def get_required_channels(self) -> List[Dict]:
        """Majburiy obuna kanallarini olish"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, channel_id, channel_title, channel_username, invite_link, added_date, is_active FROM required_channels WHERE is_active = TRUE')
        
        channels = []
        for row in cursor.fetchall():
            channels.append({
                'id': row[0],
                'channel_id': row[1],
                'channel_title': row[2],
                'channel_username': row[3],
                'invite_link': row[4],
                'added_date': row[5],
                'is_active': row[6]
            })
        
        conn.close()
        return channels
    
    def delete_required_channel(self, rc_id: int) -> bool:
        """Majburiy obuna kanalini o'chirish (faolsizlantirish)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('UPDATE required_channels SET is_active = FALSE WHERE id = ?', (rc_id,))
            conn.commit()
            affected = cursor.rowcount
            conn.close()
            return affected > 0
        except Exception as e:
            print(f"Kanalni o'chirishda xatolik: {e}")
            return False

    def update_required_channel_invite_link(self, rc_id: int, invite_link: str) -> bool:
        """Kanal uchun invite_link qiymatini yangilash"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('UPDATE required_channels SET invite_link = ? WHERE id = ?', (invite_link, rc_id))
            conn.commit()
            affected = cursor.rowcount
            conn.close()
            return affected > 0
        except Exception as e:
            print(f"invite_link yangilashda xatolik: {e}")
            return False
    
    def get_statistics(self) -> Dict:
        """Statistikani olish"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Kitoblar soni
        cursor.execute('SELECT COUNT(*) FROM books')
        books_count = cursor.fetchone()[0]
        
        # Foydalanuvchilar soni
        cursor.execute('SELECT COUNT(*) FROM users')
        users_count = cursor.fetchone()[0]
        
        # Guruhlar soni
        cursor.execute('SELECT COUNT(*) FROM groups')
        groups_count = cursor.fetchone()[0]
        
        # Majburiy obuna kanallari soni
        cursor.execute('SELECT COUNT(*) FROM required_channels WHERE is_active = TRUE')
        channels_count = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'books_count': books_count,
            'users_count': users_count,
            'groups_count': groups_count,
            'channels_count': channels_count
        }

    def get_all_user_ids(self) -> List[int]:
        """Barcha foydalanuvchi chat_id larini olish"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users')
        ids = [row[0] for row in cursor.fetchall()]
        conn.close()
        return ids

    def get_all_group_ids(self) -> List[int]:
        """Barcha guruh chat_id larini olish (faollar)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT id FROM groups WHERE is_active = TRUE')
        except Exception:
            cursor.execute('SELECT id FROM groups')
        ids = [row[0] for row in cursor.fetchall()]
        conn.close()
        return ids

    def add_book_file(self, book_id: int, file_id: str, file_type: str,
                      file_size: int | None = None,
                      storage_message_id: int | None = None,
                      storage_chat_id: str | None = None) -> bool:
        """Kitobga tegishli fayl (qism) qo'shish"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO book_files (book_id, file_id, file_type, file_size, storage_message_id, storage_chat_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (book_id, file_id, file_type, file_size, storage_message_id, storage_chat_id))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Kitob faylini qo'shishda xatolik: {e}")
            return False

    def get_book_files(self, book_id: int, file_type: str | None = None) -> List[Dict]:
        """Belgilangan kitobga tegishli barcha qism fayllarini olish"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        if file_type:
            cursor.execute('''
                SELECT id, file_id, file_type, file_size, storage_message_id, storage_chat_id
                FROM book_files
                WHERE book_id = ? AND file_type = ?
                ORDER BY id
            ''', (book_id, file_type))
        else:
            cursor.execute('''
                SELECT id, file_id, file_type, file_size, storage_message_id, storage_chat_id
                FROM book_files
                WHERE book_id = ?
                ORDER BY id
            ''', (book_id,))
        files = []
        for row in cursor.fetchall():
            files.append({
                'id': row[0],
                'file_id': row[1],
                'file_type': row[2],
                'file_size': row[3],
                'storage_message_id': row[4],
                'storage_chat_id': row[5]
            })
        conn.close()
        return files

    def get_book_by_id(self, book_id: int) -> Optional[Dict]:
        """Bitta kitob ma'lumotlarini olish"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, title, author, file_id, file_type, file_size, upload_date,
                   uploader_id, description, storage_message_id, storage_chat_id,
                   COALESCE(is_multi_part, 0)
            FROM books
            WHERE id = ?
        ''', (book_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {
            'id': row[0],
            'title': row[1],
            'author': row[2],
            'file_id': row[3],
            'file_type': row[4],
            'file_size': row[5],
            'upload_date': row[6],
            'uploader_id': row[7],
            'description': row[8],
            'storage_message_id': row[9],
            'storage_chat_id': row[10],
            'is_multi_part': bool(row[11])
        }
