"""
Botni ishga tushirish uchun qo'shimcha fayl
"""
import os
import sys

# Loyiha papkasini Python path ga qo'shish
project_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_dir)

# Asosiy faylni ishga tushirish
if __name__ == "__main__":
    from main import main
    import asyncio
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot to'xtatildi")
    except Exception as e:
        print(f"Xatolik: {e}")
