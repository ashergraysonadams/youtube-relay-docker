FROM python:3.11-slim

# تقليل حجم الصورة
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# تثبيت المتطلبات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# إعداد المشروع
WORKDIR /app
COPY . .

# متغيرات البيئة (اختياري)
ENV PYTHONDONTWRITEBYTECODE=1

# تنفيذ السكربت عند التشغيل
CMD ["python", "stream.py"]
