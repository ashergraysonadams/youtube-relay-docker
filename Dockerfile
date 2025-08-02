# استخدام صورة Python الرسمية
FROM python:3.11-slim

# تثبيت ffmpeg والأدوات الأساسية
RUN apt-get update && apt-get install -y \
    ffmpeg curl git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# تعيين مجلّد العمل داخل الحاوية
WORKDIR /app

# نسخ ملفات المشروع إلى الحاوية
COPY . .

# تثبيت الحزم من requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# تشغيل التطبيق باستخدام Uvicorn على منفذ 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
