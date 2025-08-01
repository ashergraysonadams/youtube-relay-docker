# استخدام صورة Python الرسمية
FROM python:3.11-slim

# تثبيت بعض الأدوات الأساسية و ffmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg curl git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# تعيين مجلّد العمل داخل الحاوية
WORKDIR /app

# نسخ الملفات إلى الحاوية
COPY . .

# تثبيت الحزم المطلوبة من requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# تعيين السكربت الرئيسي
CMD ["python", "main.py"]
