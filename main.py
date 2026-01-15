import os
import uvicorn
import requests
import time
import json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from playwright.sync_api import sync_playwright

app = FastAPI()

# --- 1. HTML ویب پیج (UI) ---
# یہ وہ پیج ہے جو آپ کو براؤزر میں نظر آئے گا
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Jazz Drive Debugger</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: monospace; background: #1e1e1e; color: #00ff00; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        input { padding: 10px; width: 70%; background: #333; color: white; border: 1px solid #444; }
        button { padding: 10px 20px; cursor: pointer; background: #007bff; color: white; border: none; font-weight: bold; }
        button#copyBtn { background: #28a745; margin-left: 10px; }
        #logs { 
            background: black; border: 1px solid #444; padding: 15px; 
            height: 400px; overflow-y: scroll; white-space: pre-wrap; 
            margin-top: 20px; font-size: 14px;
        }
        .error { color: #ff4444; }
        .success { color: #00ff00; }
        .info { color: #00ccff; }
        .warning { color: #ffbb33; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🛠️ Jazz Drive API Debugger</h2>
        <p>اپنا نمبر درج کریں اور ٹیسٹ شروع کریں:</p>
        
        <input type="text" id="phone" placeholder="03001234567" value="03027665767">
        <button onclick="startTest()">Start Test</button>
        <button id="copyBtn" onclick="copyLogs()">Copy Logs</button>
        
        <div id="logs">Waiting to start...</div>
    </div>

    <script>
        async function startTest() {
            const phone = document.getElementById('phone').value;
            const logDiv = document.getElementById('logs');
            logDiv.innerHTML = "Initializing Test...\\n";
            
            // لائیو سٹریم API کال
            const response = await fetch(`/debug-stream?phone=${phone}`);
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                const text = decoder.decode(value);
                logDiv.innerHTML += text;
                logDiv.scrollTop = logDiv.scrollHeight; // Auto scroll
            }
        }

        function copyLogs() {
            const logs = document.getElementById('logs').innerText;
            navigator.clipboard.writeText(logs);
            alert("Logs copied to clipboard!");
        }
    </script>
</body>
</html>
"""

# --- 2. روٹس (Routes) ---

@app.get("/")
def home():
    """HTML پیج دکھائیں"""
    return HTMLResponse(content=HTML_TEMPLATE)

@app.get("/debug-stream")
def debug_stream(phone: str):
    """یہ فنکشن لائن بائی لائن لاگز بھیجے گا تاکہ ٹائم آؤٹ نہ ہو"""
    return StreamingResponse(run_debug_process(phone), media_type="text/event-stream")

# --- 3. اصلی لاجک (Generator Function) ---
def run_debug_process(phone):
    yield f"🚀 Process Started for: {phone}\n"
    yield f"--------------------------------------------------\n"
    
    # 1. براؤزر لانچ کریں
    yield "Step 1: Launching Playwright Browser (Headless)...\n"
    session_id = None
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.set_default_timeout(60000) # 60 سیکنڈ ٹائم آؤٹ

            # 2. کلاؤڈ یو آر ایل کھولیں
            target_url = "https://cloud.jazzdrive.com.pk"
            yield f"Step 2: Navigating to {target_url}...\n"
            
            try:
                page.goto(target_url)
                yield f"ℹ️ Page Loaded. Current URL: {page.url}\n"
                
                # 3. ری ڈائریکٹ کا انتظار
                yield "Step 3: Waiting for Redirect (ID generation)...\n"
                
                # ہم کسی بھی URL کا انتظار کریں گے جس میں 'id=' ہو
                try:
                    page.wait_for_url("**id=*", timeout=45000)
                    yield f"✅ Redirect Detected!\n"
                except Exception as wait_err:
                    yield f"⚠️ Wait timeout, checking URL anyway...\n"

                final_url = page.url
                yield f"📍 Landed on URL: {final_url}\n"

                # 4. آئی ڈی نکالنا
                if "id=" in final_url:
                    parts = final_url.split("id=")
                    if len(parts) > 1:
                        session_id = parts[1].split("&")[0]
                        yield f"🎉 SUCCESS: Found Session ID: {session_id}\n"
                    else:
                        yield f"❌ ERROR: 'id=' found but could not split string.\n"
                else:
                    yield f"❌ ERROR: No 'id=' parameter found in final URL.\n"
                    # پیج کا ٹائٹل بھی چیک کر لیتے ہیں ڈیبگنگ کے لیے
                    title = page.title()
                    yield f"📄 Page Title was: {title}\n"

            except Exception as e:
                yield f"❌ BROWSER ERROR: {str(e)}\n"
            finally:
                browser.close()
                yield "Step 4: Browser Closed.\n"

        # 5. اگر آئی ڈی ملی ہے تو ریکوسٹ بھیجیں
        if session_id:
            yield f"--------------------------------------------------\n"
            yield f"Step 5: Sending API Request to Jazz...\n"
            
            api_url = f"https://jazzdrive.com.pk/oauth2/signup.php?id={session_id}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
                "Origin": "https://jazzdrive.com.pk",
                "Referer": "https://jazzdrive.com.pk",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            data = {
                "msisdn": phone,
                "enrichment_status": ""
            }

            yield f"🔗 API URL: {api_url}\n"
            yield f"📤 Payload: {json.dumps(data)}\n"
            
            try:
                resp = requests.post(api_url, data=data, headers=headers, timeout=30)
                yield f"📥 Response Status: {resp.status_code}\n"
                yield f"📄 Response Body: {resp.text[:500]} ... (truncated)\n" # صرف پہلے 500 الفاظ دکھائیں
                
                if resp.status_code in [200, 302]:
                     yield f"✅ RESULT: Request Sent Successfully.\n"
                else:
                     yield f"⚠️ RESULT: Server returned error code.\n"
            except Exception as req_err:
                yield f"❌ REQUEST ERROR: {str(req_err)}\n"

        else:
            yield f"⛔ STOPPING: Could not get ID, skipping API call.\n"

    except Exception as fatal_e:
        yield f"🔥 FATAL ERROR: {str(fatal_e)}\n"
    
    yield f"--------------------------------------------------\n"
    yield "🏁 TEST FINISHED.\n"

# --- Railway Start Command ---
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
