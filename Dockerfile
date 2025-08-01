# استخدم صورة بايثون خفيفة
FROM python:3.10-slim

# تثبيت الأدوات المطلوبة مثل ffmpeg و youtube-dl
RUN apt-get update && \
    apt-get install -y ffmpeg curl && \
    curl -L https://yt-dl.org/downloads/latest/youtube-dl -o /usr/local/bin/youtube-dl && \
    chmod a+rx /usr/local/bin/youtube-dl && \
    rm -rf /var/lib/apt/lists/*

# تحديد مجلد العمل داخل الحاوية
WORKDIR /app

# نسخ ملف المتطلبات وتثبيته
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع
COPY . .

# الأمر الذي يتم تنفيذه عند تشغيل الحاوية
CMD ["python", "stream.py"]
