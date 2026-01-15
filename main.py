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

# --- In-Memory Database ---
# یہ ڈیٹا تب تک رہے گا جب تک سرور چل رہا ہے
db = {}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://jazzdrive.com.pk",
    "Referer": "https://jazzdrive.com.pk/"
}

# --- HTML Template (with Persistence Fix) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Jazz Drive Bot (Stable)</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { background-color: #0d1117; color: #e6edf3; font-family: monospace; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; }
        .panel { background: #161b22; border: 1px solid #30363d; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        
        input { background: #0d1117; border: 1px solid #30363d; color: #fff; padding: 12px; width: 60%; border-radius: 4px; margin-bottom: 10px; }
        button { background: #238636; color: white; border: none; padding: 12px 24px; cursor: pointer; font-weight: bold; border-radius: 4px; }
        button:disabled { background: #30363d; cursor: not-allowed; }
        
        #monitor { 
            width: 100%; min-height: 400px; background: #000; border: 2px solid #3fb950; 
            display: flex; flex-direction: column; align-items: center; justify-content: center; margin-top: 10px;
        }
        #monitor img { max-width: 100%; max-height: 500px; border: 1px solid #333; }
        .status-bar { width: 100%; background: #21262d; padding: 5px; text-align: center; font-size: 14px; color: #f0f6fc; border-bottom: 1px solid #30363d; }
        
        #logs { height: 200px; overflow-y: scroll; background: #0d1117; padding: 10px; border: 1px solid #30363d; font-size: 12px; color: #58a6ff; margin-top: 10px; }
        .hidden { display: none; }
        .error-msg { color: #ff7b72; font-weight: bold; margin-bottom: 10px; border: 1px solid #ff7b72; padding: 10px; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🤖 Jazz Bot Pro <button onclick="fullReset()" style="float:right; background:#da3633; font-size:12px; padding:5px 10px;">Clear Data</button></h2>
        
        <div class="panel" id="step1">
            <h3>Step 1: Start Session</h3>
            <input type="text" id="phone" value="03027665767" placeholder="030xxxxxxxxx">
            <button onclick="startStep1()" id="btn1">Start Browser</button>
        </div>

        <div class="panel hidden" id="step2">
            <h3>Step 2: Enter OTP</h3>
            <div id="otp-error" class="error-msg hidden">❌ Invalid OTP! Check SMS & Enter New Code.</div>
            <input type="text" id="otp" placeholder="Enter Code (Wait for Input Field)">
            <button onclick="startStep2()" id="btn2">Type OTP & Login</button>
        </div>

        <div class="panel hidden" id="step3">
            <h3>Step 3: Upload File</h3>
            <div style="color:#3fb950; margin-bottom:10px;">✅ LOGIN SUCCESSFUL! Session Active.</div>
            <input type="file" id="fileInput">
            <button onclick="uploadFile()" id="btn3">Upload & Get Link</button>
            <p id="final-link" style="color: #58a6ff; margin-top:10px; word-break: break-all; font-size: 14px;"></p>
        </div>

        <div id="live-area" class="hidden">
            <div id="monitor">
                <div class="status-bar" id="live-status">Initializing...</div>
                <img id="live-img" src="" alt="Waiting for screenshot...">
            </div>
            <div id="logs"></div>
        </div>
    </div>

    <script>
        let pollInterval = null;
        let currentKey = localStorage.getItem('session_key') || "";

        function fullReset() { localStorage.clear(); window.location.reload(); }

        // --- PERSISTENCE LOGIC (Re-Load Data on Refresh) ---
        window.onload = function() {
            const savedStep = localStorage.getItem('step');
            
            // If session exists, start polling immediately to recover logs/images
            if(currentKey) {
                document.getElementById('live-area').classList.remove('hidden');
                startPolling(currentKey);
            }

            if(savedStep === '2') {
                document.getElementById('step1').classList.add('hidden');
                document.getElementById('step2').classList.remove('hidden');
            }
            if(savedStep === '3') {
                document.getElementById('step1').classList.add('hidden');
                document.getElementById('step2').classList.add('hidden');
                document.getElementById('step3').classList.remove('hidden');
            }
        }

        async function startStep1() {
            const phone = document.getElementById('phone').value;
            // Create a unique key for this session
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
                    
                    // Recover Logs
                    if(data.logs) {
                        const l = document.getElementById('logs');
                        l.innerHTML = data.logs.map(x => `<div>> ${x}</div>`).join('');
                        l.scrollTop = l.scrollHeight;
                    }
                    // Recover Image
                    if(data.screenshot) {
                        document.getElementById('live-img').src = "data:image/jpeg;base64," + data.screenshot;
                        document.getElementById('live-status').innerText = data.last_action;
                    }

                    // Transitions
                    if(data.stage === 'step1_complete') {
                        // Don't stop polling, just update UI
                        if(localStorage.getItem('step') !== '2') {
                            localStorage.setItem('step', '2');
                            location.reload(); 
                        }
                    }

                    if(data.stage === 'login_success') {
                        clearInterval(pollInterval);
                        localStorage.setItem('step', '3');
                        localStorage.setItem('auth_data', JSON.stringify(data.auth_data));
                        location.reload();
                    }

                    if(data.stage === 'retry_otp') {
                        document.getElementById('btn2').disabled = false;
                        document.getElementById('otp').value = ""; 
                        document.getElementById('otp-error').classList.remove('hidden');
                    }
                    
                } catch(e) { console.log("Polling...", e); }
            }, 1500);
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

# Helper for Logs and Screenshots
async def update_db(key, log_msg=None, page=None, action_name=None):
    if key not in db: db[key] = {"logs": [], "screenshot": None, "stage": "init"}
    
    if log_msg:
        print(f"[{key}] {log_msg}")
        db[key]["logs"].append(log_msg)
    
    if page and action_name:
        try:
            # Capture Screenshot
            b64 = base64.b64encode(await page.screenshot(type='jpeg', quality=40)).decode()
            db[key]["screenshot"] = b64
            db[key]["last_action"] = action_name
        except Exception as e:
            print(f"Screenshot Error: {e}")

async def task_step1(phone: str, key: str):
    await update_db(key, "Launching Browser...")
    db[key]["stage"] = "running"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            # موبائل ویو پورٹ سیٹ کریں تاکہ بٹن سامنے نظر آئے
            context = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 375, "height": 812}
            )
            page = await context.new_page()

            # 1. Open URL
            await update_db(key, "Opening Jazz Cloud...", page, "Init")
            await page.goto("https://cloud.jazzdrive.com.pk", timeout=60000)
            
            # 2. WAIT FOR FULL LOAD (Important Fix)
            await update_db(key, "Waiting for Page Load...", page, "Loading...")
            await page.wait_for_load_state("networkidle") # جب تک نیٹ ورک خاموش نہ ہو
            await asyncio.sleep(3) # مزید 3 سیکنڈ احتیاطاً
            await update_db(key, "Page Fully Loaded", page, "1. Page Loaded")

            # 3. Type Number
            await update_db(key, f"Typing Number: {phone}")
            try:
                # متعدد سلیکٹرز ٹرائی کریں
                if await page.locator('input[type="tel"]').count() > 0:
                    await page.fill('input[type="tel"]', phone)
                elif await page.locator('input[name="msisdn"]').count() > 0:
                    await page.fill('input[name="msisdn"]', phone)
                else:
                    await page.fill('input', phone)
            except Exception as e:
                await update_db(key, f"Input Error: {e}")

            await asyncio.sleep(1)
            await update_db(key, "Number Typed", page, "2. Number Entered")

            # 4. Find & Click Subscribe Button
            await update_db(key, "Clicking Subscribe Button...")
            
            # بٹن کے مختلف نام ٹرائی کریں
            clicked = False
            selectors = ['button:has-text("Subscribe")', 'input[type="submit"]', 'button[type="submit"]', '.btn-primary']
            
            for sel in selectors:
                if await page.locator(sel).count() > 0:
                    await page.click(sel)
                    clicked = True
                    break
            
            if not clicked:
                # اگر کوئی خاص بٹن نہیں ملا تو پہلا بٹن دبا دو
                await page.click('button')
            
            await update_db(key, "Button Clicked", page, "3. Button Clicked")

            # 5. Wait for Redirect to Verify Page
            await update_db(key, "Waiting for Redirect...")
            await page.wait_for_url("**verify.php**", timeout=60000)
            
            # Capture ID
            real_id = page.url.split("id=")[1].split("&")[0]
            db[key]["real_jazz_id"] = real_id
            db[key]["stage"] = "step1_complete"
            
            await update_db(key, f"Redirected! ID Captured.", page, "4. Verify Page Reached")
            await browser.close()

    except Exception as e:
        db[key]["stage"] = "failed"
        db[key]["error"] = str(e)
        await update_db(key, f"Fatal Error: {str(e)}")


async def task_step2(otp: str, key: str):
    real_id = db.get(key, {}).get("real_jazz_id")
    if not real_id:
        await update_db(key, "Error: Session ID Lost. Restart Step 1.")
        return

    await update_db(key, f"Starting Verification on ID: {real_id}...")
    db[key]["stage"] = "running"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(user_agent=HEADERS["User-Agent"])
            page = await context.new_page()

            # 1. Open Verify Page
            url = f"https://jazzdrive.com.pk/verify.php?id={real_id}"
            await page.goto(url, timeout=45000)
            await page.wait_for_load_state("networkidle")
            await update_db(key, "Verify Page Loaded", page, "5. Ready for OTP")

            # 2. Type OTP
            await update_db(key, "Typing OTP (Auto-Submit)...")
            await page.type('input', otp, delay=200) # ٹائپ کرتے ہوئے تصویر
            await update_db(key, "OTP Entered", page, "6. OTP Typed")
            
            # 3. Wait for Result
            await update_db(key, "Waiting for Dashboard...")
            try:
                # A. Success Case
                await page.wait_for_url("https://cloud.jazzdrive.com.pk/**", timeout=10000)
                await update_db(key, "Redirect Success!", page, "7. Login Success")
                
                # Extract Keys
                cookies = await context.cookies()
                c_dict = {c['name']: c['value'] for c in cookies}
                if "validationkey=" in page.url.lower():
                    from urllib.parse import urlparse, parse_qs
                    qs = parse_qs(urlparse(page.url).query)
                    for k,v in qs.items():
                         if k.lower() == 'validationkey': c_dict['validationKey'] = v[0]
                
                db[key]["auth_data"] = c_dict
                db[key]["stage"] = "login_success"

            except:
                # B. Failure/Retry Case
                await update_db(key, "No Redirect. Checking Errors...", page, "8. Stuck/Error")
                
                # Check text for "Invalid"
                content = await page.inner_text("body")
                if any(x in content.lower() for x in ["invalid", "incorrect", "wrong", "failed"]):
                    await update_db(key, "DETECTED: Invalid OTP Error")
                    db[key]["stage"] = "retry_otp"
                elif "verify.php" in page.url:
                    await update_db(key, "Still on Verify Page -> Assuming Invalid OTP")
                    db[key]["stage"] = "retry_otp"
                else:
                    db[key]["stage"] = "failed"
                    db[key]["error"] = "Unknown Error"

            await browser.close()
    except Exception as e:
        db[key]["stage"] = "failed"
        db[key]["error"] = str(e)


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
