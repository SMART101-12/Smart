import os
import shutil

# پوشه‌ها و فایل‌های اضافی برای حذف
JUNK_DIRS = [
    '.venv_broken',
    '.venv_old',
]

JUNK_FILES = [
    'list_structure.py',
    'quick_summary.py',
]

print("🧹 شروع پاک‌سازی ریپازیتوری...")

for folder in JUNK_DIRS:
    if os.path.exists(folder):
        print(f"🗑️ حذف پوشه اضافه: {folder}")
        shutil.rmtree(folder, ignore_errors=True)

for file in JUNK_FILES:
    if os.path.exists(file):
        print(f"🗑️ حذف فایل موقت: {file}")
        try:
            os.remove(file)
        except Exception:
            pass

# مطمئن شدن از وجود .gitkeep در پوشه runtime
os.makedirs('runtime', exist_ok=True)
with open('runtime/.gitkeep', 'w', encoding='utf-8') as f:
    pass

print("✅ پاک‌سازی لوکال با موفقیت انجام شد.")
