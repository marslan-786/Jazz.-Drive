FROM python:3.9-slim

# Install Chrome and dependencies
RUN apt-get update && apt-get install -y wget gnupg2 unzip curl

# Install Google Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' \
    && apt-get update \
    && apt-get install -y google-chrome-stable

# Set working directory
WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy App Code
COPY . .

# Environment Variable for Display (Headless Chrome needs this sometimes)
ENV DISPLAY=:99

# Run Command (Gunicorn for production)
CMD ["gunicorn", "main:app", "-b", "0.0.0.0:$PORT", "--timeout", "120"]
