import os
import uvicorn
import requests
import json
import base64
import asyncio
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from playwright.async_api import async_playwright

app = FastAPI()

# --- Database ---
db = {}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://jazzdrive.com.pk",
    "Referer": "https://jazzdrive.com.pk/"
}

# --- UI Template ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Jazz Drive Bot (Smart Retry)</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { background-color: #0d1117; color: #e6edf3; font-family: monospace; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        .panel { background: #161b22; border: 1px solid #30363d; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        
        input { background: #0d1117; border: 1px solid #30363d; color: #fff; padding: 12px; width: 60%; border-radius: 4px; margin-bottom: 10px; }
        button { background: #238636; color: white; border: none; padding: 12px 24px; cursor: pointer; font-weight: bold; border-radius: 4px; }
        button:disabled { background: #30363d; cursor: not-allowed; }
        button.reset { background: #da3633; float: right; padding: 5px 10px; font-size: 12px; }
        
        #monitor { 
            width: 100%; min-height: 300px; background: #000; border: 2px solid #3fb950; 
            display: flex; flex-direction: column; align-items: center; justify-content: center;
        }
        #monitor img { max-width: 100%; max-height: 400px; }
        .status-bar { width: 100%; background: #21262d; padding: 5px; text-align: center; font-size: 12px; color: #8b949e; }
        
        #logs { height: 150px; overflow-y: scroll; background: #0d1117; padding: 10px; border: 1px solid #30363d; font-size: 12px; color: #58a6ff; margin-top: 10px; }
        .hidden { display: none; }
        .error-msg { color: #f85149; font-weight: bold; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🤖 Jazz Bot <button class="reset" onclick="resetApp()">New Session</button></h2>
        
        <div class="panel" id="step1">
            <h3>Step 1: Send OTP</h3>
            <input type="text" id="phone" placeholder="030xxxxxxxxx" value="03027665767">
            <button onclick="startStep1()" id="btn1">Start & Send OTP</button>
        </div>

        <div class="panel hidden" id="step2">
            <h3>Step 2: Enter OTP</h3>
            <div id="otp-status" class="error-msg hidden">Invalid OTP! Jazz sent a new one. Enter it below:</div>
            <input type="text" id="otp" placeholder="Enter Code">
            <button onclick="startStep2()" id="btn2">Login</button>
        </div>

        <div class="panel hidden" id="step3">
            <h3>Step 3: Upload</h3>
            <div style="color:#3fb950; margin-bottom:10px;">✅ LOGIN SUCCESSFUL</div>
            <input type="file" id="fileInput">
            <button onclick="uploadFile()" id="btn3">Upload & Get Link</button>
            <p id="final-link" style="color: #58a6ff; margin-top:10px; word-break: break-all;"></p>
        </div>

        <div id="live-area" class="hidden">
            <div id="monitor">
                <img id="live-img" src="" alt="Live Feed">
                <div class="status-bar" id="live-status">Waiting...</div>
            </div>
            <div id="logs"></div>
        </div>
    </div>

    <script>
        let pollInterval = null;
        let currentSessionKey = localStorage.getItem('session_key') || "";

        function resetApp() { localStorage.clear(); window.location.reload(); }

        // Restore State logic
        window.onload = function() {
            if(localStorage.getItem('step') === '2') {
                document.getElementById('step1').classList.add('hidden');
                document.getElementById('step2').classList.remove('hidden');
                document.getElementById('live-area').classList.remove('hidden');
                if(currentSessionKey) startPolling(currentSessionKey);
            }
            if(localStorage.getItem('step') === '3') {
                document.getElementById('step1').classList.add('hidden');
                document.getElementById('step2').classList.add('hidden');
                document.getElementById('step3').classList.remove('hidden');
            }
        }

        async function startStep1() {
            const phone = document.getElementById('phone').value;
            currentSessionKey = "sess_" + Date.now();
            localStorage.setItem('session_key', currentSessionKey);

            document.getElementById('btn1').disabled = true;
            document.getElementById('live-area').classList.remove('hidden');
            
            await fetch('/api/step1', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({phone: phone, session_key: currentSessionKey})
            });
            startPolling(currentSessionKey);
        }

        async function startStep2() {
            const otp = document.getElementById('otp').value;
            document.getElementById('btn2').disabled = true;
            document.getElementById('otp-status').classList.add('hidden'); // Hide error if any
            
            await fetch('/api/step2', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({otp: otp, session_key: currentSessionKey})
            });
            startPolling(currentSessionKey);
        }

        function startPolling(key) {
            if(pollInterval) clearInterval(pollInterval);
            pollInterval = setInterval(async () => {
                try {
                    const res = await fetch(`/api/status/${key}`);
                    const data = await res.json();
                    
                    // Logs & Screenshot
                    if(data.logs) {
                        const l = document.getElementById('logs');
                        l.innerHTML = data.logs.map(x => `<div>> ${x}</div>`).join('');
                        l.scrollTop = l.scrollHeight;
                    }
                    if(data.screenshot) {
                        document.getElementById('live-img').src = "data:image/jpeg;base64," + data.screenshot;
                        document.getElementById('live-status').innerText = data.last_action || "Working...";
                    }

                    // Handle Success Step 1
                    if(data.stage === 'step1_complete') {
                        clearInterval(pollInterval);
                        localStorage.setItem('step', '2');
                        location.reload();
                    }

                    // Handle Login Success
                    if(data.stage === 'login_success') {
                        clearInterval(pollInterval);
                        localStorage.setItem('step', '3');
                        localStorage.setItem('auth_data', JSON.stringify(data.auth_data));
                        location.reload();
                    }

                    // --- RETRY LOGIC (Invalid OTP) ---
                    if(data.stage === 'retry_otp') {
                        clearInterval(pollInterval);
                        document.getElementById('btn2').disabled = false;
                        document.getElementById('otp').value = ""; // Clear input
                        document.getElementById('otp-status').innerText = "❌ Invalid OTP! Jazz sent a new one. Try again.";
                        document.getElementById('otp-status').classList.remove('hidden');
                        alert("Invalid OTP! Check SMS for new code.");
                    }

                    // Handle Fatal Error
                    if(data.stage === 'failed') {
                        clearInterval(pollInterval);
                        alert("Fatal Error: " + data.error);
                    }

                } catch(e) { console.log(e); }
            }, 1000);
        }

        async function uploadFile() {
            const file = document.getElementById('fileInput').files[0];
            const authData = localStorage.getItem('auth_data');
            const fd = new FormData();
            fd.append("file", file);
            fd.append("cookies_json", authData);
            
            document.getElementById('btn3').innerText = "Uploading...";
            document.getElementById('btn3').disabled = true;
            
            const res = await fetch('/api/upload', {method:'POST', body:fd});
            const d = await res.json();
            
            if(d.status === 'success') {
                document.getElementById('final-link').innerHTML = `Direct Link: <a href="${d.jazz_link}" target="_blank">${d.jazz_link}</a>`;
            } else {
                alert(d.message);
            }
            document.getElementById('btn3').disabled = false;
            document.getElementById('btn3').innerText = "Upload & Get Link";
        }
    </script>
</body>
</html>
"""

# --- Backend Logic ---

class BrowserReq(BaseModel):
    phone: str = ""
    otp: str = ""
    session_key: str

async def task_step1(phone: str, key: str):
    db[key] = {"logs": ["Started Step 1..."], "screenshot": None, "stage": "running"}
    
    def log(m): db[key]["logs"].append(m); print(f"[{key}] {m}")
    async def shot(p, a):
        try: db[key]["screenshot"] = base64.b64encode(await p.screenshot(type='jpeg', quality=40)).decode(); db[key]["last_action"] = a
        except: pass

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = await browser.new_page(user_agent=HEADERS["User-Agent"])

            log("Opening Jazz Cloud...")
            await page.goto("https://cloud.jazzdrive.com.pk", timeout=60000)
            await shot(page, "Home Page")

            # Input Number
            try:
                await page.wait_for_selector('input', timeout=30000)
                # Try to find input field (varies)
                await page.type('input[type="tel"]', phone)
            except:
                await page.type('input', phone) # fallback
            
            await shot(page, "Number Typed")
            await page.keyboard.press('Enter') # Submit
            
            log("Waiting for Redirect to Verify Page...")
            await page.wait_for_url("**verify.php**", timeout=60000)
            
            real_id = page.url.split("id=")[1].split("&")[0]
            db[key]["real_jazz_id"] = real_id
            db[key]["stage"] = "step1_complete"
            log(f"ID Captured: {real_id}")
            
            await browser.close()
    except Exception as e:
        db[key]["stage"] = "failed"; db[key]["error"] = str(e)


async def task_step2(otp: str, key: str):
    real_id = db.get(key, {}).get("real_jazz_id")
    if not real_id: return
    
    # لاگز صاف کریں لیکن سٹیج رننگ رکھیں
    db[key]["logs"] = [f"Attempting OTP: {otp} on ID: {real_id}"]
    db[key]["stage"] = "running"
    
    def log(m): db[key]["logs"].append(m); print(f"[{key}] {m}")
    async def shot(p, a):
        try: db[key]["screenshot"] = base64.b64encode(await p.screenshot(type='jpeg', quality=40)).decode(); db[key]["last_action"] = a
        except: pass

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(user_agent=HEADERS["User-Agent"])
            page = await context.new_page()

            verify_url = f"https://jazzdrive.com.pk/verify.php?id={real_id}"
            log(f"Opening {verify_url}")
            await page.goto(verify_url, timeout=45000)
            await shot(page, "Verify Page")

            # Type OTP with delay for Auto-Submit
            log("Typing OTP (Auto-Submit)...")
            try:
                await page.type('input[name="otp"]', otp, delay=200)
            except:
                await page.type('input', otp, delay=200)
            
            await shot(page, "OTP Entered")
            
            # Wait for Result (Redirect OR Error)
            log("Waiting for result...")
            try:
                # 1. Success Case: Redirect to Cloud
                await page.wait_for_url("https://cloud.jazzdrive.com.pk/**", timeout=10000)
                log("Success! Redirected.")
                
                # Get Keys
                cookies = await context.cookies()
                c_dict = {c['name']: c['value'] for c in cookies}
                if "validationkey=" in page.url.lower():
                    from urllib.parse import urlparse, parse_qs
                    c_dict['validationKey'] = parse_qs(urlparse(page.url).query)['validationKey'][0]
                
                db[key]["auth_data"] = c_dict
                db[key]["stage"] = "login_success"

            except:
                # 2. Failure Case: Still on Verify Page (Timeout)
                log("Dashboard not loaded. Checking for Invalid OTP...")
                await shot(page, "Check Error")
                
                # اگر ہم ابھی بھی verify.php پر ہیں، تو اس کا مطلب OTP غلط ہے
                if "verify.php" in page.url:
                    log("Stuck on Verify Page -> INVALID OTP Detected")
                    db[key]["stage"] = "retry_otp" # This triggers the loop in frontend
                else:
                    db[key]["stage"] = "failed"
                    db[key]["error"] = "Unknown Error"

            await browser.close()
    except Exception as e:
        db[key]["stage"] = "failed"; db[key]["error"] = str(e)


# --- Routes ---
@app.get("/")
def home(): return HTMLResponse(HTML_TEMPLATE)

@app.post("/api/step1")
async def step1(req: BrowserReq, tasks: BackgroundTasks):
    tasks.add_task(task_step1, req.phone, req.session_key)
    return {"status": "ok"}

@app.post("/api/step2")
async def step2(req: BrowserReq, tasks: BackgroundTasks):
    tasks.add_task(task_step2, req.otp, req.session_key)
    return {"status": "ok"}

@app.get("/api/status/{key}")
def status(key: str): return db.get(key, {})

@app.post("/api/upload")
async def upload_file_api(file: UploadFile = File(...), cookies_json: str = Form(...)):
    # ... (Same Upload Logic as before) ...
    try:
        cookies = json.loads(cookies_json)
        v_key = cookies.get('validationKey') or cookies.get('validationkey')
        session = requests.Session(); session.cookies.update(cookies)
        ts = str(int(asyncio.get_event_loop().time()))
        files = {'data': (None, json.dumps({"data":{"name":file.filename,"size":0,"modificationdate":ts,"contenttype":file.content_type}}), 'application/json'), 'file': (file.filename, await file.read(), file.content_type)}
        r1 = session.post("https://cloud.jazzdrive.com.pk/sapi/upload", params={"action":"save","acceptasynchronous":"true","validationkey":v_key}, files=files, headers=HEADERS)
        fid = r1.json()['id']
        r2 = session.post("https://cloud.jazzdrive.com.pk/sapi/media", params={"action":"get","origin":"omh,dropbox","validationkey":v_key}, json={"data":{"ids":[fid],"fields":["url"]}}, headers=HEADERS)
        return {"status":"success", "jazz_link":r2.json()['data']['media'][0]['url']}
    except Exception as e: return {"status":"error", "message":str(e)}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
