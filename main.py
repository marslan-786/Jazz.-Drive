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

# --- Database (In-Memory) ---
# یہ ڈیٹا تب تک رہے گا جب تک سرور چل رہا ہے
db = {}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://jazzdrive.com.pk",
    "Referer": "https://jazzdrive.com.pk/"
}

# --- HTML UI Template ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Jazz Drive Bot (Final Fix)</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { background-color: #0d1117; color: #e6edf3; font-family: monospace; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; }
        .panel { background: #161b22; border: 1px solid #30363d; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        
        input { background: #0d1117; border: 1px solid #30363d; color: #fff; padding: 12px; width: 60%; border-radius: 4px; margin-bottom: 10px; }
        button { background: #238636; color: white; border: none; padding: 12px 24px; cursor: pointer; font-weight: bold; border-radius: 4px; }
        button:disabled { background: #30363d; cursor: not-allowed; }
        
        #monitor { 
            width: 100%; min-height: 350px; background: #000; border: 2px solid #3fb950; 
            display: flex; flex-direction: column; align-items: center; justify-content: center; margin-top: 10px;
        }
        #monitor img { max-width: 100%; max-height: 450px; border: 1px solid #333; }
        .status-bar { width: 100%; background: #21262d; padding: 5px; text-align: center; font-size: 12px; color: #8b949e; }
        
        #logs { height: 150px; overflow-y: scroll; background: #0d1117; padding: 10px; border: 1px solid #30363d; font-size: 12px; color: #58a6ff; margin-top: 10px; }
        .hidden { display: none; }
        .error-box { background: #5a1e1e; color: #ffadad; padding: 10px; margin-bottom: 10px; border-radius: 4px; border: 1px solid #ff0000; text-align: center; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🤖 Jazz Bot <button onclick="resetApp()" style="float:right; background:#da3633; font-size:12px; padding:5px 10px;">Reset</button></h2>
        
        <div class="panel" id="step1">
            <h3>Step 1: Start Session</h3>
            <input type="text" id="phone" value="03027665767" placeholder="030xxxxxxxxx">
            <button onclick="startStep1()" id="btn1">Send OTP</button>
        </div>

        <div class="panel hidden" id="step2">
            <h3>Step 2: Enter OTP</h3>
            <div id="otp-error" class="error-box hidden">❌ Invalid OTP! Jazz sent a new one. Try again.</div>
            <input type="text" id="otp" placeholder="Enter Code (Auto-Submit)">
            <button onclick="startStep2()" id="btn2">Verify Login</button>
        </div>

        <div class="panel hidden" id="step3">
            <h3>Step 3: Upload File</h3>
            <div style="color:#3fb950; margin-bottom:10px;">✅ LOGIN SUCCESSFUL! Keys Saved.</div>
            <input type="file" id="fileInput">
            <button onclick="uploadFile()" id="btn3">Upload & Get Link</button>
            <p id="final-link" style="color: #58a6ff; margin-top:10px; word-break: break-all; font-size: 14px;"></p>
        </div>

        <div id="live-area" class="hidden">
            <div id="monitor">
                <img id="live-img" src="" alt="Connecting...">
                <div class="status-bar" id="live-status">Initializing...</div>
            </div>
            <div id="logs"></div>
        </div>
    </div>

    <script>
        let pollInterval = null;
        let currentKey = localStorage.getItem('session_key') || "";

        function resetApp() { localStorage.clear(); window.location.reload(); }

        window.onload = function() {
            if(localStorage.getItem('step') === '2') {
                document.getElementById('step1').classList.add('hidden');
                document.getElementById('step2').classList.remove('hidden');
                document.getElementById('live-area').classList.remove('hidden');
                if(currentKey) startPolling(currentKey);
            }
            if(localStorage.getItem('step') === '3') {
                document.getElementById('step1').classList.add('hidden');
                document.getElementById('step2').classList.add('hidden');
                document.getElementById('step3').classList.remove('hidden');
            }
        }

        async function startStep1() {
            const phone = document.getElementById('phone').value;
            currentKey = "sess_" + Date.now();
            localStorage.setItem('session_key', currentKey);

            document.getElementById('btn1').disabled = true;
            document.getElementById('live-area').classList.remove('hidden');
            
            await fetch('/api/step1', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({phone: phone, session_key: currentKey})
            });
            startPolling(currentKey);
        }

        async function startStep2() {
            const otp = document.getElementById('otp').value;
            document.getElementById('btn2').disabled = true;
            document.getElementById('otp-error').classList.add('hidden');
            
            await fetch('/api/step2', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({otp: otp, session_key: currentKey})
            });
            startPolling(currentKey);
        }

        function startPolling(key) {
            if(pollInterval) clearInterval(pollInterval);
            pollInterval = setInterval(async () => {
                try {
                    const res = await fetch(`/api/status/${key}`);
                    const data = await res.json();
                    
                    if(data.logs) {
                        const l = document.getElementById('logs');
                        l.innerHTML = data.logs.map(x => `<div>> ${x}</div>`).join('');
                        l.scrollTop = l.scrollHeight;
                    }
                    if(data.screenshot) {
                        document.getElementById('live-img').src = "data:image/jpeg;base64," + data.screenshot;
                        document.getElementById('live-status').innerText = data.last_action;
                    }

                    if(data.stage === 'step1_complete') {
                        clearInterval(pollInterval);
                        localStorage.setItem('step', '2');
                        location.reload();
                    }

                    if(data.stage === 'login_success') {
                        clearInterval(pollInterval);
                        localStorage.setItem('step', '3');
                        localStorage.setItem('auth_data', JSON.stringify(data.auth_data));
                        location.reload();
                    }

                    // --- RETRY LOGIC (یہ ہے وہ چیز جو آپ چاہتے ہیں) ---
                    if(data.stage === 'retry_otp') {
                        clearInterval(pollInterval);
                        document.getElementById('btn2').disabled = false;
                        document.getElementById('otp').value = ""; 
                        document.getElementById('otp-error').classList.remove('hidden');
                        // Sound alert if needed
                        alert("Invalid OTP! Check SMS for new code.");
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
                document.getElementById('final-link').innerHTML = `Direct Link:<br><a href="${d.jazz_link}" target="_blank">${d.jazz_link}</a>`;
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
    db[key] = {"logs": ["Starting Browser..."], "screenshot": None, "stage": "running"}
    
    def log(m): db[key]["logs"].append(m); print(f"[{key}] {m}")
    async def shot(p, a):
        try: db[key]["screenshot"] = base64.b64encode(await p.screenshot(type='jpeg', quality=30)).decode(); db[key]["last_action"] = a
        except: pass

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = await browser.new_page(user_agent=HEADERS["User-Agent"])

            log("Opening Jazz Cloud...")
            await page.goto("https://cloud.jazzdrive.com.pk", timeout=60000)
            await shot(page, "Loaded Cloud")

            # Input Number
            log(f"Typing Number: {phone}")
            try:
                # Try finding input by type or generic input
                await page.wait_for_selector('input', timeout=30000)
                await page.type('input[type="tel"]', phone)
            except:
                await page.type('input', phone)
            
            await shot(page, "Number Typed")
            await page.keyboard.press('Enter')
            
            log("Waiting for Verify Page...")
            await page.wait_for_url("**verify.php**", timeout=60000)
            
            # Extract ID
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
    
    # لاگز ری سیٹ کریں
    db[key]["logs"] = [f"Trying OTP: {otp}"]
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

            # Go to Verify Page
            url = f"https://jazzdrive.com.pk/verify.php?id={real_id}"
            log("Opening Verify Page...")
            await page.goto(url, timeout=45000)
            await shot(page, "Verify Page")

            # Type OTP (Slowly for Auto-Submit)
            log(f"Typing OTP: {otp}...")
            try:
                await page.type('input[name="otp"]', otp, delay=200) # 200ms delay per key
            except:
                await page.type('input', otp, delay=200)
            
            await shot(page, "OTP Entered")
            
            # Wait for Result (Redirect OR Error Message)
            log("Waiting for response...")
            try:
                # 1. SUCCESS: Redirect to Dashboard
                await page.wait_for_url("https://cloud.jazzdrive.com.pk/**", timeout=8000) # 8 seconds wait
                log("Redirect Success! Grabbing Keys...")
                
                # Get Keys
                cookies = await context.cookies()
                c_dict = {c['name']: c['value'] for c in cookies}
                
                # Scan URL for key
                if "validationkey=" in page.url.lower():
                    from urllib.parse import urlparse, parse_qs
                    qs = parse_qs(urlparse(page.url).query)
                    for k,v in qs.items():
                         if k.lower() == 'validationkey': c_dict['validationKey'] = v[0]
                
                if c_dict.get('validationKey') or c_dict.get('validationkey'):
                    db[key]["auth_data"] = c_dict
                    db[key]["stage"] = "login_success"
                else:
                    db[key]["error"] = "Redirected but Key Missing"
                    db[key]["stage"] = "failed"

            except:
                # 2. FAILURE: Timeout implies we are stuck on Verify Page
                log("No Redirect. Checking for Error Messages...")
                await shot(page, "Stuck/Error")
                
                # Read text from page
                content = await page.inner_text("body")
                content_lower = content.lower()
                
                # Keywords for Invalid OTP
                error_keywords = ["invalid", "incorrect", "wrong", "mismatch", "failed", "error"]
                
                found = False
                for kw in error_keywords:
                    if kw in content_lower:
                        log(f"Detected Error: '{kw}'")
                        db[key]["stage"] = "retry_otp" # Trigger Retry in Frontend
                        found = True
                        break
                
                if not found:
                    # اگر کچھ نہیں ملا، پھر بھی اگر ہم verify.php پر ہیں تو مطلب OTP غلط ہی ہے
                    if "verify.php" in page.url:
                        log("Still on Verify Page -> Assuming Invalid OTP")
                        db[key]["stage"] = "retry_otp"
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
async def s1(req: BrowserReq, tasks: BackgroundTasks):
    tasks.add_task(task_step1, req.phone, req.session_key)
    return {"status": "ok"}

@app.post("/api/step2")
async def s2(req: BrowserReq, tasks: BackgroundTasks):
    tasks.add_task(task_step2, req.otp, req.session_key)
    return {"status": "ok"}

@app.get("/api/status/{key}")
def st(key: str): return db.get(key, {})

@app.post("/api/upload")
async def up(file: UploadFile = File(...), cookies_json: str = Form(...)):
    try:
        cookies = json.loads(cookies_json)
        v_key = cookies.get('validationKey') or cookies.get('validationkey')
        session = requests.Session(); session.cookies.update(cookies)
        
        # Upload
        files = {'data': (None, json.dumps({"data":{"name":file.filename,"size":0,"modificationdate":"20250101"}}), 'application/json'), 'file': (file.filename, await file.read(), file.content_type)}
        r1 = session.post("https://cloud.jazzdrive.com.pk/sapi/upload", params={"action":"save","acceptasynchronous":"true","validationkey":v_key}, files=files, headers=HEADERS)
        
        # Get Link
        fid = r1.json()['id']
        r2 = session.post("https://cloud.jazzdrive.com.pk/sapi/media", params={"action":"get","origin":"omh,dropbox","validationkey":v_key}, json={"data":{"ids":[fid],"fields":["url"]}}, headers=HEADERS)
        return {"status":"success", "jazz_link":r2.json()['data']['media'][0]['url']}
    except Exception as e: return {"status":"error", "message":str(e)}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
