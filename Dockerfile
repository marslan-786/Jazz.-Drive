# 1. New Python Version (3.11 Slim) - Faster & Modern
FROM python:3.11-slim

# 2. Install Dependencies
# apt-key کا رولا ختم کرنے کے لیے ہم سیدھا .deb فائل ڈاؤن لوڈ کر کے انسٹال کریں گے
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    ca-certificates \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 3. Install Google Chrome (Direct Method)
# یہ طریقہ سب سے محفوظ ہے، یہ لیٹسٹ کروم ڈاؤن لوڈ کرے گا اور خود ہی انسٹال کرے گا
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb

# 4. Set Working Directory
WORKDIR /app

# 5. Copy Requirements and Install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy App Code
COPY . .

# 7. Environment Variables
# ڈسپلے پورٹ اور بفرنگ بند کرنے کے لیے
ENV DISPLAY=:99
ENV PYTHONUNBUFFERED=1

# 8. Run Command
CMD ["gunicorn", "main:app", "-b", "0.0.0.0:$PORT", "--timeout", "120"]
