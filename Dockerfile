# استخدم Python base image
FROM python:3.10

# إعداد مجلد العمل داخل الكونتينر
WORKDIR /app

# نسخ كل ملفات المشروع إلى داخل الكونتينر
COPY . .

# تثبيت المتطلبات
RUN pip install --upgrade pip && pip install -r requirements.txt

# تعيين المتغير PORT اللي Cloud Run بيتوقعه
ENV PORT 8080

# تشغيل التطبيق باستخدام Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
