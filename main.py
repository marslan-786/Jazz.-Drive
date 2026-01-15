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

# --- Global State for Live Feed ---
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

# --- Frontend UI (CCTV Style) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Jazz Drive Full Browser Automation</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { background-color: #0d1117; color: #e6edf3; font-family: 'Segoe UI', monospace; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        .panel { background: #161b22; border: 1px solid #30363d; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        
        input { background: #0d1117; border: 1px solid #30363d; color: #fff; padding: 12px; width: 60%; border-radius: 4px; margin-bottom: 10px; }
        button { background: #238636; color: white; border: none; padding: 12px 24px; cursor: pointer; font-weight: bold; border-radius: 4px; }
        button:disabled { background: #30363d; cursor: not-allowed; }
        button.reset { background: #da3633; float: right; padding: 5px 10px; font-size: 12px; }
        
        /* Live Monitor Screen */
        #monitor { 
            width: 100%; min-height: 350px; background: #000; border: 2px solid #3fb950; 
            display: flex; flex-direction: column; align-items: center; justify-content: center; position: relative;
        }
        #monitor img { max-width: 100%; max-height: 400px; border: 1px solid #333; }
        .status-bar { width: 100%; background: #21262d; padding: 5px; text-align: center; font-size: 12px; color: #8b949e; }
        
        #logs { height: 150px; overflow-y: scroll; background: #0d1117; padding: 10px; border: 1px solid #30363d; font-size: 12px; color: #58a6ff; margin-top: 10px; font-family: monospace; }
        
        .hidden { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🤖 Jazz Drive Human Mode <button class="reset" onclick="resetApp()">New Session</button></h2>
        
        <div class="panel" id="step1">
            <h3>Step 1: Number Input (via Browser)</h3>
            <input type="text" id="phone" placeholder="030xxxxxxxxx" value="03027665767">
            <button onclick="startBrowserStep1()" id="btn1">Start Browser & Send OTP</button>
        </div>

        <div class="panel hidden" id="step2">
            <h3>Step 2: Enter OTP (Auto-Submit)</h3>
            <input type="text" id="otp" placeholder="Enter 4-digit Code">
            <button onclick="startBrowserStep2()" id="btn2">Type OTP & Login</button>
        </div>

        <div class="panel hidden" id="step3">
            <h3>Step 3: Upload File</h3>
            <div style="background: #238636; padding: 10px; border-radius: 4px; margin-bottom: 10px;">LOGIN SUCCESSFUL!</div>
            <input type="file" id="fileInput">
            <button onclick="uploadFile()" id="btn3">Upload & Get Link</button>
            <p id="final-link" style="word-break: break-all; color: #58a6ff; margin-top:10px;"></p>
        </div>

        <div id="live-area" class="hidden">
            <h3>🔴 Live Browser Feed</h3>
            <div id="monitor">
                <img id="live-img" src="" alt="Connecting to Browser...">
                <div class="status-bar" id="live-status">Waiting...</div>
            </div>
            <div id="logs"></div>
        </div>

    </div>

    <script>
        // --- Logic ---
        let pollInterval = null;
        let currentSessionId = localStorage.getItem('session_id') || "";

        function resetApp() { localStorage.clear(); window.location.reload(); }

        // Restore State
        if(localStorage.getItem('step') === '2') {
            document.getElementById('step1').classList.add('hidden');
            document.getElementById('step2').classList.remove('hidden');
            document.getElementById('live-area').classList.remove('hidden');
            if(currentSessionId) startPolling(currentSessionId);
        }
        if(localStorage.getItem('step') === '3') {
            document.getElementById('step1').classList.add('hidden');
            document.getElementById('step2').classList.add('hidden');
            document.getElementById('step3').classList.remove('hidden');
        }

        async function startBrowserStep1() {
            const phone = document.getElementById('phone').value;
            // Generate a random ID for tracking this specific browser session
            currentSessionId = "session_" + Date.now();
            localStorage.setItem('session_id', currentSessionId);

            document.getElementById('btn1').disabled = true;
            document.getElementById('live-area').classList.remove('hidden');
            
            // Start Backend Task
            await fetch('/api/step1-browser', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({phone: phone, session_key: currentSessionId})
            });

            startPolling(currentSessionId);
        }

        async function startBrowserStep2() {
            const otp = document.getElementById('otp').value;
            // We need the Real ID (from Jazz URL) which Step 1 should have saved in DB
            // But for tracking the UI, we use our currentSessionId
            
            document.getElementById('btn2').disabled = true;
            
            await fetch('/api/step2-browser', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({otp: otp, session_key: currentSessionId})
            });
            
            // Polling continues/restarts
            startPolling(currentSessionId);
        }

        function startPolling(key) {
            if(pollInterval) clearInterval(pollInterval);
            pollInterval = setInterval(async () => {
                try {
                    const res = await fetch(`/api/status/${key}`);
                    const data = await res.json();
                    
                    // Update Logs
                    if(data.logs) {
                        const l = document.getElementById('logs');
                        l.innerHTML = data.logs.map(x => `<div>> ${x}</div>`).join('');
                        l.scrollTop = l.scrollHeight;
                    }
                    // Update Image
                    if(data.screenshot) {
                        document.getElementById('live-img').src = "data:image/jpeg;base64," + data.screenshot;
                        document.getElementById('live-status').innerText = data.last_action || "Processing...";
                    }

                    // Handle Step 1 Completion
                    if(data.stage === 'step1_complete') {
                        clearInterval(pollInterval);
                        localStorage.setItem('step', '2');
                        // Backend stored the Jazz Real ID, no need to pass it manually if DB handles it
                        location.reload(); 
                    }

                    // Handle Step 2 Completion
                    if(data.stage === 'login_success') {
                        clearInterval(pollInterval);
                        localStorage.setItem('step', '3');
                        localStorage.setItem('auth_data', JSON.stringify(data.auth_data));
                        location.reload();
                    }
                    
                    if(data.stage === 'failed') {
                        clearInterval(pollInterval);
                        alert("Failed: " + data.error);
                        localStorage.clear();
                        location.reload();
                    }

                } catch(e) { console.log(e); }
            }, 1000);
        }

        async function uploadFile() {
            // ... (Same upload logic as before) ...
            const file = document.getElementById('fileInput').files[0];
            const authData = localStorage.getItem('auth_data');
            const fd = new FormData();
            fd.append("file", file);
            fd.append("cookies_json", authData);
            
            document.getElementById('btn3').disabled = true;
            document.getElementById('btn3').innerText = "Uploading...";
            
            const res = await fetch('/api/upload', {method:'POST', body:fd});
            const d = await res.json();
            
            if(d.status === 'success') {
                document.getElementById('final-link').innerHTML = `<a href="${d.jazz_link}" target="_blank">${d.jazz_link}</a>`;
            } else {
                alert(d.message);
            }
            document.getElementById('btn3').disabled = false;
        }
    </script>
</body>
</html>
"""

# --- Backend Worker Logic ---

# In-Memory DB
# Structure: { "session_123": { "logs": [], "screenshot": "base64", "real_jazz_id": "...", "auth_data": {}, "stage": "running" } }
db = {}

class BrowserReq(BaseModel):
    phone: str = ""
    otp: str = ""
    session_key: str # Our local UI tracker

# --- TASK 1: OPEN BROWSER -> TYPE NUMBER -> CLICK -> GET ID ---
async def task_step1(phone: str, key: str):
    db[key] = {"logs": ["Initializing Browser..."], "screenshot": None, "stage": "running"}
    
    def log(m): db[key]["logs"].append(m); print(m)
    async def shot(p, action):
        try:
            b = await p.screenshot(type='jpeg', quality=40)
            db[key]["screenshot"] = base64.b64encode(b).decode('utf-8')
            db[key]["last_action"] = action
        except: pass

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(user_agent=HEADERS["User-Agent"])
            page = await context.new_page()

            # 1. Open Cloud URL
            log("Opening cloud.jazzdrive.com.pk...")
            await page.goto("https://cloud.jazzdrive.com.pk", timeout=60000)
            await shot(page, "Page Loaded")

            # 2. Wait for Redirect to Signup/Login Page
            log("Waiting for redirection...")
            # We expect a redirect to oauth2/signup.php or similar
            try:
                await page.wait_for_url("**signup.php**", timeout=30000)
                log("Redirected to Signup Page!")
            except:
                log("Warning: Maybe already on input page?")
            
            await shot(page, "On Input Page")

            # 3. Find Input & Type Number
            log(f"Typing Number: {phone}")
            # Try multiple selectors for input
            input_sel = 'input[type="tel"]'
            if await page.locator(input_sel).count() == 0:
                input_sel = 'input[name="msisdn"]' # fallback
            
            await page.fill(input_sel, phone)
            await shot(page, "Number Typed")

            # 4. Click Submit/Subscribe
            log("Searching for Submit Button...")
            # User said "Subscribe" button, usually it's type submit or has text
            # We will click the first button found
            await page.click('button') 
            await shot(page, "Button Clicked")

            # 5. Wait for Redirect to Verify Page (to capture ID)
            log("Waiting for Verify Page to load...")
            await page.wait_for_url("**verify.php**", timeout=45000)
            
            final_url = page.url
            log(f"Landed on: {final_url}")
            await shot(page, "Verify Page Reached")

            # Extract ID
            if "id=" in final_url:
                real_id = final_url.split("id=")[1].split("&")[0]
                db[key]["real_jazz_id"] = real_id
                db[key]["stage"] = "step1_complete"
                log(f"SUCCESS! ID Captured: {real_id}")
            else:
                db[key]["stage"] = "failed"
                db[key]["error"] = "ID not found in URL"

            await browser.close()

    except Exception as e:
        log(f"Error: {e}")
        db[key]["stage"] = "failed"
        db[key]["error"] = str(e)


# --- TASK 2: OPEN VERIFY LINK -> TYPE OTP (AUTO SUBMIT) -> GET COOKIES ---
async def task_step2(otp: str, key: str):
    # Retrieve Real ID from Step 1
    real_id = db.get(key, {}).get("real_jazz_id")
    if not real_id:
        db[key] = {"logs": ["Error: Session ID lost. Restart."], "stage": "failed", "error": "ID Lost"}
        return

    # Reset logs for Step 2
    db[key]["logs"] = ["Resuming Browser for Step 2...", f"Target ID: {real_id}"]
    db[key]["stage"] = "running"
    
    def log(m): db[key]["logs"].append(m); print(m)
    async def shot(p, act):
        try:
            b = await p.screenshot(type='jpeg', quality=40)
            db[key]["screenshot"] = base64.b64encode(b).decode('utf-8')
            db[key]["last_action"] = act
        except: pass

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(user_agent=HEADERS["User-Agent"])
            page = await context.new_page()

            # 1. Go Directly to Verify Page
            target = f"https://jazzdrive.com.pk/verify.php?id={real_id}"
            log(f"Navigating to {target}")
            await page.goto(target, timeout=60000)
            await shot(page, "Verify Page Loaded")

            # 2. Type OTP (Slowly for Auto-Submit)
            log(f"Typing OTP: {otp} (Slowly)...")
            
            # Focus on input
            try:
                await page.click('input[name="otp"]')
            except:
                await page.click('input') # Fallback
            
            # Type character by character with delay to trigger Auto-Submit
            await page.type('input', otp, delay=200) 
            await shot(page, "OTP Typed")
            
            log("OTP Entered. Waiting for Auto-Redirect...")

            # 3. Wait for Cloud Dashboard
            try:
                await page.wait_for_url("https://cloud.jazzdrive.com.pk/**", timeout=60000)
                log("Redirect Successful! Dashboard Loaded.")
                await shot(page, "Login Success")
            except Exception as e:
                log("Timeout waiting for dashboard. Checking URL...")
                await shot(page, "Stuck/Timeout")

            # 4. Grab Cookies/Keys
            cookies = await context.cookies()
            c_dict = {c['name']: c['value'] for c in cookies}
            
            # Check for Key in URL (Backup)
            if "validationkey=" in page.url.lower():
                from urllib.parse import urlparse, parse_qs
                parsed = parse_qs(urlparse(page.url).query)
                for k, v in parsed.items():
                    if k.lower() == 'validationkey':
                        c_dict['validationKey'] = v[0]

            if c_dict.get('validationKey') or c_dict.get('validationkey'):
                db[key]["auth_data"] = c_dict
                db[key]["stage"] = "login_success"
                log("Validation Key FOUND!")
            else:
                db[key]["stage"] = "failed"
                db[key]["error"] = "Login page loaded but Key missing"

            await browser.close()

    except Exception as e:
        log(f"Error: {e}")
        db[key]["stage"] = "failed"
        db[key]["error"] = str(e)


# --- Routes ---

@app.get("/")
def home(): return HTMLResponse(HTML_TEMPLATE)

@app.post("/api/step1-browser")
async def start_s1(req: BrowserReq, tasks: BackgroundTasks):
    tasks.add_task(task_step1, req.phone, req.session_key)
    return {"status": "started"}

@app.post("/api/step2-browser")
async def start_s2(req: BrowserReq, tasks: BackgroundTasks):
    tasks.add_task(task_step2, req.otp, req.session_key)
    return {"status": "started"}

@app.get("/api/status/{key}")
def status(key: str):
    return db.get(key, {"status": "unknown"})

@app.post("/api/upload")
async def upload_file_api(file: UploadFile = File(...), cookies_json: str = Form(...)):
    # ... (Same Upload Logic as before) ...
    # مختصر کر رہا ہوں، آپ اپنا پچھلا کوڈ یہاں ڈالیں
    try:
        cookies = json.loads(cookies_json)
        v_key = cookies.get('validationKey') or cookies.get('validationkey')
        session = requests.Session(); session.cookies.update(cookies)
        # 1. Upload
        files = {'data': (None, json.dumps({"data":{"name":file.filename, "size":0, "modificationdate":"20250101"}}), 'application/json'), 
                 'file': (file.filename, await file.read(), file.content_type)}
        r1 = session.post("https://cloud.jazzdrive.com.pk/sapi/upload", 
                          params={"action":"save","acceptasynchronous":"true","validationkey":v_key}, files=files, headers=HEADERS)
        fid = r1.json()['id']
        # 2. Get Link
        r2 = session.post("https://cloud.jazzdrive.com.pk/sapi/media", params={"action":"get","origin":"omh,dropbox","validationkey":v_key}, 
                          json={"data":{"ids":[fid],"fields":["url"]}}, headers=HEADERS)
        url = r2.json()['data']['media'][0]['url']
        return {"status":"success", "jazz_link":url}
    except Exception as e: return {"status":"error", "message":str(e)}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
