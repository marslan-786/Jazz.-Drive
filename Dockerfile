# 1. مائیکروسافٹ کا آفیشل Playwright امیج استعمال کریں (اس میں سب کچھ انسٹال ہے)
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

# 2. ورکنگ ڈائریکٹری سیٹ کریں
WORKDIR /app

# 3. ریکوائرمنٹس فائل کاپی کریں اور انسٹال کریں
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. باقی سارا کوڈ کاپی کریں
COPY . .

# 5. یہ وہ کمانڈ ہے جو سرور چلائے گا
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
