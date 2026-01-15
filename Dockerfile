# 1. ہم لیٹسٹ (Latest) امیج استعمال کریں گے تاکہ ورژن کا مسئلہ نہ آئے
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# 2. ورکنگ ڈائریکٹری سیٹ کریں
WORKDIR /app

# 3. لائبریریز انسٹال کریں
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. احتیاطاً براؤزر دوبارہ انسٹال کریں (یہ سب سے اہم سٹیپ ہے)
# یہ لائن اس بات کو یقینی بنائے گی کہ براؤزر ہر حال میں موجود ہو
RUN playwright install chromium
RUN playwright install-deps

# 5. کوڈ کاپی کریں
COPY . .

# 6. سرور چلائیں
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
