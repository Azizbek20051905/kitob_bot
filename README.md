# Telegram Kitob Bot

Bu bot orqali foydalanuvchilar kitoblar qidirishlari mumkin. Bot faqat Aiogram kutubxonasi yordamida yaratilgan.

## Xususiyatlar

- 📚 Kitob qidirish tizimi
- 📁 PDF va audio fayllarni qo'llab-quvvatlash
- 🧩 Bir kitob uchun bir nechta qism (E-kitob/AUDIO) qo'shish
- 🔒 Majburiy obuna tizimi
- 👨‍💼 Admin panel
- 📊 Statistika
- 💾 SQLite ma'lumotlar bazasi
- 🎯 Shaxsiy chat va guruhlarda ishlash

## O'rnatish

1. **Kerakli kutubxonalarni o'rnating:**
```bash
pip install -r requirements.txt
```

2. **Konfiguratsiya faylini yarating:**
```bash
cp .env.example .env
```

3. **`.env` faylini to'ldiring:**
```
BOT_TOKEN=your_bot_token_here
ADMIN_ID=your_admin_user_id_here
STORAGE_CHANNEL_ID=@your_storage_channel_id
```

4. **Botni ishga tushiring:**
```bash
python main.py
```

## Konfiguratsiya

### Bot Token
BotFather dan olingan bot tokeni.

### Admin ID
Admin foydalanuvchining Telegram ID si.

### Storage Channel ID
Kitob fayllarini saqlash uchun kanal ID si yoki username.

## Foydalanish

### Foydalanuvchilar uchun:
1. `/start` - Botni ishga tushirish
2. `/help` - Yordam olish
3. Kitob nomini yozish - Kitob qidirish
4. Qismli kitoblar uchun kerakli formatni tanlash (E-kitob yoki Audio)

### Admin uchun:
1. `/admin` - Admin panelini ochish
2. Kitob qo'shish - Fayl yuklash orqali
   - 🧩 Qismli kitob rejimi orqali kitob nomini kiritib, hujjat yoki audio qismlarni aralash tashlash mumkin
3. Kitob o'chirish - Admin panel orqali
4. Statistika ko'rish
5. Majburiy obuna kanallarini boshqarish

## Fayl turlari

Bot quyidagi fayl turlarini qo'llab-quvvatlaydi:
- **PDF:** `.pdf`
- **Audio:** `.mp3`, `.wav`, `.ogg`, `.m4a`, `.flac`

## Loyiha tuzilishi

```
python kitob bot/
├── main.py              # Asosiy fayl
├── config.py            # Konfiguratsiya
├── requirements.txt     # Kerakli kutubxonalar
├── .env.example        # Konfiguratsiya namunasi
├── handlers/           # Handler fayllari
│   ├── __init__.py
│   ├── basic.py        # Asosiy handlerlar
│   ├── books.py        # Kitob handlerlari
│   ├── groups.py       # Guruh handlerlari
│   └── admin.py        # Admin handlerlari
├── database/           # Ma'lumotlar bazasi
│   ├── __init__.py
│   └── db.py           # Database moduli
└── utils/              # Yordamchi funksiyalar
    ├── __init__.py
    ├── helpers.py      # Yordamchi funksiyalar
    └── subscription.py # Obuna tekshirish
```

## Muhim eslatmalar

1. **Storage Channel:** Bot fayllarni saqlash uchun maxsus kanalga yuklaydi. Bu kanalda bot admin bo'lishi kerak.

2. **Majburiy Obuna:** Agar majburiy obuna kanallari qo'shilgan bo'lsa, foydalanuvchilar botdan foydalanishdan oldin ularga obuna bo'lishlari shart. Agar kanallar qo'shilmagan bo'lsa, foydalanuvchilar bemalol foydalanishlari mumkin.

3. **Fayl Hajmi:** Maksimal fayl hajmi 50 MB.

4. **Admin Huquqlari:** Faqat admin fayl yuklashi va botni boshqarishi mumkin.

5. **Avtomatik Kitob Qo'shish:** Admin ko'p kitob qo'shish uchun avtomatik rejimni ishlatishi mumkin. Bu rejimda bot fayl nomidan kitob nomi va muallifni avtomatik aniqlaydi.

## Xatoliklar

Agar bot ishlamasa:
1. Bot tokenini tekshiring
2. Storage channel ID ni tekshiring
3. Bot kanalda admin ekanligini tekshiring
4. Kerakli kutubxonalar o'rnatilganini tekshiring

## Aloqa

Savollar bo'lsa admin bilan bog'laning.
