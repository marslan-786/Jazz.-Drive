import os
import uvicorn
import requests
import json
import base64
import asyncio
import time
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from playwright.async_api import async_playwright

app = FastAPI()

# --- Global Storage (For Live Updates) ---
# یہ میموری میں ڈیٹا رکھے گا تاکہ ریفریش پر بھی نظر آئے اور لائیو اپڈیٹ ہو
sessions_db = {}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://jazzdrive.com.pk",
    "Referer": "https://jazzdrive.com.pk/"
}

class NumberRequest(BaseModel):
    phone: str

class OtpRequest(BaseModel):
    otp: str
    session_id: str

# --- Frontend UI (Improved) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Jazz Drive CCTV Bot</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { background-color: #0d1117; color: #e6edf3; font-family: monospace; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        .panel { background: #161b22; border: 1px solid #30363d; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        
        input { background: #0d1117; border: 1px solid #30363d; color: #fff; padding: 12px; width: 60%; border-radius: 4px; margin-bottom: 10px; }
        button { background: #238636; color: white; border: none; padding: 12px 24px; cursor: pointer; font-weight: bold; border-radius: 4px; }
        button:disabled { background: #30363d; cursor: not-allowed; }
        button.reset { background: #da3633; float: right; }
        
        #cctv-screen { 
            width: 100%; height: 400px; background: #000; border: 2px solid #3fb950; 
            display: flex; align-items: center; justify-content: center; position: relative;
        }
        #cctv-screen img { max-width: 100%; max-height: 100%; }
        .live-badge { position: absolute; top: 10px; right: 10px; background: red; color: white; padding: 2px 8px; font-size: 10px; border-radius: 4px; animation: blink 1s infinite; }
        
        #logs { height: 150px; overflow-y: scroll; background: #0d1117; padding: 10px; border: 1px solid #30363d; font-size: 12px; color: #8b949e; margin-top: 10px; }
        
        @keyframes blink { 50% { opacity: 0; } }
        .hidden { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🕵️ Jazz Drive Live Monitor <button class="reset" onclick="resetApp()">Reset</button></h2>
        
        <div class="panel" id="step1">
            <h3>Step 1: Send OTP</h3>
            <input type="text" id="phone" placeholder="030xxxxxxxxx">
            <button onclick="sendOtp()" id="btn1">Send Code</button>
        </div>

        <div class="panel hidden" id="step2">
            <h3>Step 2: Verify & Watch Live</h3>
            <input type="text" id="otp" placeholder="Enter OTP (e.g 1234)">
            <button onclick="startVerification()" id="btn2">Start Verification</button>
            
            <div style="margin-top: 20px;">
                <div id="cctv-screen">
                    <div class="live-badge">LIVE FEED</div>
                    <img id="live-img" src="" alt="Waiting for feed...">
                </div>
                <div id="logs">Logs will appear here...</div>
            </div>
            <div id="status-msg" style="color: #3fb950; margin-top: 10px; font-weight: bold;"></div>
        </div>

        <div class="panel hidden" id="step3">
            <h3>Step 3: Upload File</h3>
            <p>Login Successful! Keys Saved.</p>
            <input type="file" id="fileInput">
            <button onclick="uploadFile()" id="btn3">Upload & Get Link</button>
            <p id="final-link" style="word-break: break-all; color: #58a6ff; margin-top:10px;"></p>
        </div>
    </div>

    <script>
        // --- Persistence Logic (Save State) ---
        function saveState(key, val) { localStorage.setItem(key, val); }
        function getState(key) { return localStorage.getItem(key); }
        
        let pollInterval = null;

        // Load State on Refresh
        window.onload = function() {
            const savedStep = getState('step') || '1';
            const savedPhone = getState('phone');
            const savedSession = getState('session_id');
            const savedAuth = getState('auth_data');
            
            if(savedPhone) document.getElementById('phone').value = savedPhone;
            
            if(savedStep === '2' && savedSession) {
                document.getElementById('step1').classList.add('hidden');
                document.getElementById('step2').classList.remove('hidden');
                // اگر ویرفکیشن چل رہی تھی تو پولنگ دوبارہ شروع کریں
                startPolling(savedSession);
            }
            if(savedStep === '3') {
                document.getElementById('step1').classList.add('hidden');
                document.getElementById('step2').classList.add('hidden');
                document.getElementById('step3').classList.remove('hidden');
            }
        };

        function resetApp() {
            localStorage.clear();
            window.location.reload();
        }

        async function sendOtp() {
            const phone = document.getElementById('phone').value;
            document.getElementById('btn1').disabled = true;
            
            try {
                const res = await fetch('/api/send-otp', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({phone})
                });
                const data = await res.json();
                if(data.status === 'success') {
                    saveState('step', '2');
                    saveState('phone', phone);
                    saveState('session_id', data.session_id);
                    location.reload(); // ریفریش تاکہ سٹیٹ پکی ہو جائے
                } else {
                    alert("Error: " + data.message);
                    document.getElementById('btn1').disabled = false;
                }
            } catch(e) { alert(e); }
        }

        async function startVerification() {
            const otp = document.getElementById('otp').value;
            const sessionId = getState('session_id');
            
            document.getElementById('btn2').disabled = true;
            document.getElementById('logs').innerHTML = "<div>Starting Background Process...</div>";

            // بیک گراؤنڈ ٹاسک شروع کریں
            await fetch('/api/verify-otp', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({otp: otp, session_id: sessionId})
            });

            // پولنگ شروع کریں (ہر 2 سیکنڈ بعد اپڈیٹ)
            startPolling(sessionId);
        }

        function startPolling(sessionId) {
            if(pollInterval) clearInterval(pollInterval);
            
            pollInterval = setInterval(async () => {
                try {
                    const res = await fetch(`/api/status/${sessionId}`);
                    const data = await res.json();
                    
                    // 1. Update Logs
                    if(data.logs) {
                        const logDiv = document.getElementById('logs');
                        logDiv.innerHTML = data.logs.map(l => `<div>> ${l}</div>`).join('');
                        logDiv.scrollTop = logDiv.scrollHeight;
                    }

                    // 2. Update CCTV Image
                    if(data.screenshot) {
                        document.getElementById('live-img').src = "data:image/png;base64," + data.screenshot;
                    }

                    // 3. Check Status
                    if(data.status === 'completed') {
                        clearInterval(pollInterval);
                        document.getElementById('status-msg').innerText = "LOGIN SUCCESSFUL!";
                        saveState('step', '3');
                        saveState('auth_data', JSON.stringify(data.auth_data));
                        setTimeout(() => location.reload(), 2000);
                    }
                    if(data.status === 'failed') {
                        clearInterval(pollInterval);
                        document.getElementById('status-msg').innerText = "FAILED: " + data.error;
                        document.getElementById('status-msg').style.color = "red";
                        document.getElementById('btn2').disabled = false;
                    }
                } catch(e) { console.log("Polling error", e); }
            }, 2000); // ہر 2 سیکنڈ بعد چیک کرے گا
        }
        
        async function uploadFile() {
            const file = document.getElementById('fileInput').files[0];
            const authData = getState('auth_data');
            
            const formData = new FormData();
            formData.append("file", file);
            formData.append("cookies_json", authData);
            
            document.getElementById('btn3').innerText = "Uploading...";
            document.getElementById('btn3').disabled = true;

            const res = await fetch('/api/upload', { method: 'POST', body: formData });
            const data = await res.json();
            
            if(data.status === 'success') {
                document.getElementById('final-link').innerHTML = `Direct Link: <a href="${data.jazz_link}" target="_blank">${data.jazz_link}</a>`;
                document.getElementById('btn3').innerText = "Upload Another";
            } else {
                alert("Upload Failed: " + data.message);
            }
            document.getElementById('btn3').disabled = false;
        }
    </script>
</body>
</html>
"""

# --- Backend Logic (Background Worker) ---

# یہ فنکشن بیک گراؤنڈ میں چلے گا اور sessions_db کو اپڈیٹ کرتا رہے گا
async def run_browser_verification(session_id: str, otp: str):
    sessions_db[session_id] = {
        "status": "running", 
        "logs": ["Starting Browser..."], 
        "screenshot": None,
        "auth_data": None
    }
    
    def log(msg):
        sessions_db[session_id]["logs"].append(msg)
        print(f"[{session_id}] {msg}")

    # سکرین شاٹ لینے والا فنکشن
    async def capture(page):
        try:
            b64 = base64.b64encode(await page.screenshot(type='jpeg', quality=50)).decode('utf-8')
            sessions_db[session_id]["screenshot"] = b64
        except: pass

    try:
        async with async_playwright() as p:
            log("Launching Headless Browser...")
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
            context = await browser.new_context(user_agent=HEADERS["User-Agent"])
            page = await context.new_page()

            # --- CCTV Loop (Continuously take screenshots) ---
            # ہم ایک الگ ٹاسک لگا دیتے ہیں جو ہر 1 سیکنڈ بعد تصویر لے
            async def auto_capture():
                while sessions_db[session_id]["status"] == "running":
                    await capture(page)
                    await asyncio.sleep(1.5) # ہر 1.5 سیکنڈ بعد تصویر
            
            capture_task = asyncio.create_task(auto_capture())

            # 1. Open Verify Page
            verify_url = f"https://jazzdrive.com.pk/verify.php?id={session_id}"
            log(f"Navigating to {verify_url}")
            await page.goto(verify_url, timeout=60000)
            
            # 2. Type OTP
            log(f"Typing OTP: {otp}")
            try:
                await page.fill('input[name="otp"]', otp)
                await page.keyboard.press('Enter')
                log("Pressed Enter key...")
            except Exception as e:
                log(f"Input Error: {e}")

            # 3. Wait for Redirect
            log("Waiting for Jazz Cloud Dashboard...")
            try:
                await page.wait_for_url("https://cloud.jazzdrive.com.pk/**", timeout=45000)
                log("Successfully landed on Dashboard!")
            except Exception as e:
                log("Redirect Timeout! Trying to scan anyway...")

            # 4. Extract Cookies
            log("Extracting Keys...")
            cookies = await context.cookies()
            cookies_dict = {c['name']: c['value'] for c in cookies}
            
            # URL Scan
            if "validationkey=" in page.url.lower():
                from urllib.parse import urlparse, parse_qs
                parsed = parse_qs(urlparse(page.url).query)
                for k, v in parsed.items():
                    if k.lower() == 'validationkey':
                        cookies_dict['validationKey'] = v[0]

            # Final Check
            if cookies_dict.get('validationKey') or cookies_dict.get('validationkey'):
                log("Validation Key FOUND!")
                sessions_db[session_id]["status"] = "completed"
                sessions_db[session_id]["auth_data"] = cookies_dict
            else:
                log("Login seemed OK but Key NOT found.")
                sessions_db[session_id]["status"] = "failed"
                sessions_db[session_id]["error"] = "Key Missing"

            # Stop Capture
            capture_task.cancel()
            await browser.close()

    except Exception as e:
        log(f"Critical Error: {str(e)}")
        sessions_db[session_id]["status"] = "failed"
        sessions_db[session_id]["error"] = str(e)


# --- API Routes ---

@app.get("/")
def home():
    return HTMLResponse(HTML_TEMPLATE)

@app.post("/api/send-otp")
async def send_otp_api(req: NumberRequest):
    # یہ وہی پرانا کوڈ ہے، اس میں کوئی تبدیلی نہیں کیونکہ یہ ٹھیک کام کر رہا ہے
    session_id = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = await browser.new_page(user_agent=HEADERS["User-Agent"])
            await page.goto("https://cloud.jazzdrive.com.pk", timeout=30000)
            await page.wait_for_url("**id=*", timeout=30000)
            if "id=" in page.url:
                session_id = page.url.split("id=")[1].split("&")[0]
            await browser.close()
        
        if not session_id: return {"status": "fail", "message": "ID extraction failed"}
        
        requests.post(f"https://jazzdrive.com.pk/oauth2/signup.php?id={session_id}", 
                      data={"msisdn": req.phone, "enrichment_status": ""}, headers=HEADERS)
        return {"status": "success", "session_id": session_id}
    except Exception as e: return {"status": "error", "message": str(e)}

@app.post("/api/verify-otp")
async def start_verification(req: OtpRequest, background_tasks: BackgroundTasks):
    """
    یہ اب پروسیس کو روک کر نہیں رکھے گا۔
    یہ 'بیک گراؤنڈ' میں ٹاسک شروع کرے گا اور فوراً جواب دے گا۔
    """
    background_tasks.add_task(run_browser_verification, req.session_id, req.otp)
    return {"status": "started", "message": "Background verification started"}

@app.get("/api/status/{session_id}")
def get_status(session_id: str):
    """فرنٹ اینڈ اس API کو بار بار کال کرے گا ڈیٹا لینے کے لیے"""
    if session_id in sessions_db:
        return sessions_db[session_id]
    return {"status": "not_found"}

@app.post("/api/upload")
async def upload_file_api(file: UploadFile = File(...), cookies_json: str = Form(...)):
    # آپ کا پرانا اپ لوڈ کوڈ یہاں آئے گا (میں نے مختصر کر دیا ہے)
    try:
        cookies = json.loads(cookies_json)
        v_key = cookies.get('validationKey') or cookies.get('validationkey')
        if not v_key: return {"status":"fail", "message":"Missing Key"}
        
        # ... Upload Logic Same as before ...
        # (یہاں وہی requests.post کوڈ استعمال کریں جو پہلے دیا تھا)
        
        # صرف ٹیسٹ کے لیے ڈمی رسپانس (آپ اپنا اصل کوڈ یہاں پیسٹ کریں)
        # return {"status": "success", "jazz_link": "https://dummy-link..."}
        
        # ORIGINAL LOGIC RE-INSERTION (Short Version):
        session = requests.Session()
        session.cookies.update(cookies)
        ts = str(int(time.time()))
        files = {
            'data': (None, json.dumps({"data": {"name": file.filename, "size": 0, "modificationdate": ts, "contenttype": file.content_type}}), 'application/json'),
            'file': (file.filename, await file.read(), file.content_type)
        }
        resp = session.post("https://cloud.jazzdrive.com.pk/sapi/upload", 
                            params={"action":"save", "acceptasynchronous":"true", "validationkey": v_key}, 
                            files=files, headers=HEADERS)
        fid = resp.json().get("id")
        
        link_resp = session.post("https://cloud.jazzdrive.com.pk/sapi/media",
                                 params={"action":"get", "origin":"omh,dropbox", "validationkey": v_key},
                                 json={"data":{"ids":[fid],"fields":["url"]}}, headers=HEADERS)
        url = link_resp.json()["data"]["media"][0]["url"]
        return {"status": "success", "jazz_link": url}

    except Exception as e: return {"status":"error", "message": str(e)}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
