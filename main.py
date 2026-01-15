import os
import uvicorn
import requests
import json
import base64
import asyncio
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from playwright.async_api import async_playwright

app = FastAPI()

# --- Config ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://jazzdrive.com.pk",
    "Referer": "https://jazzdrive.com.pk/"
}

# --- Models ---
class NumberRequest(BaseModel):
    phone: str

class OtpRequest(BaseModel):
    otp: str
    session_id: str

# --- Frontend UI ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Jazz Drive Spy Mode</title>
    <style>
        body { background-color: #0d1117; color: #c9d1d9; font-family: monospace; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; }
        .panel { background: #161b22; border: 1px solid #30363d; padding: 20px; border-radius: 6px; margin-bottom: 20px; }
        
        input { background: #0d1117; border: 1px solid #30363d; color: #fff; padding: 10px; width: 60%; }
        button { background: #238636; color: white; border: none; padding: 10px 20px; cursor: pointer; font-weight: bold; }
        button:disabled { background: #30363d; }
        
        #console { background: #000; border: 1px solid #333; height: 200px; overflow-y: scroll; padding: 10px; color: #0f0; font-size: 12px; margin-bottom: 20px; }
        
        /* Screenshot Gallery */
        #gallery { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; }
        .shot-card { background: #21262d; padding: 5px; border-radius: 4px; width: 200px; text-align: center; }
        .shot-card img { width: 100%; border: 1px solid #30363d; cursor: pointer; }
        .shot-card span { display: block; font-size: 11px; color: #8b949e; margin-top: 5px; }
        
        /* Modal for full view */
        #modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); justify-content: center; align-items: center; z-index: 1000; }
        #modal img { max-width: 90%; max-height: 90%; border: 2px solid white; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🕵️ Jazz Drive Capture Mode</h2>
        
        <div class="panel">
            <div id="step1">
                <p>1. Phone Number:</p>
                <input type="text" id="phone" value="03027665767">
                <button onclick="runStep1()" id="btn1">Send OTP</button>
            </div>

            <div id="step2" style="display:none;">
                <p>2. Enter OTP (Wait for Screenshots):</p>
                <input type="text" id="otp" placeholder="1234">
                <button onclick="runStep2()" id="btn2">Verify & Capture</button>
            </div>
            
            <div id="step3" style="display:none;">
                <p>3. Upload File:</p>
                <input type="file" id="fileInput">
                <button onclick="runStep3()" id="btn3">Upload</button>
            </div>
        </div>

        <h3>📟 Live Logs:</h3>
        <div id="console">System Ready...</div>

        <h3>📸 Browser Evidence Gallery:</h3>
        <div id="gallery"></div>
    </div>

    <div id="modal" onclick="this.style.display='none'">
        <img id="modalImg" src="">
    </div>

    <script>
        let sessionId = "";
        let authData = null;

        function log(msg) {
            const c = document.getElementById('console');
            c.innerHTML += `<div>> ${msg}</div>`;
            c.scrollTop = c.scrollHeight;
        }

        function addImage(b64, label) {
            const g = document.getElementById('gallery');
            const div = document.createElement('div');
            div.className = 'shot-card';
            div.innerHTML = `
                <img src="data:image/png;base64,${b64}" onclick="viewFull(this.src)">
                <span>${label}</span>
            `;
            g.appendChild(div);
        }

        function viewFull(src) {
            document.getElementById('modalImg').src = src;
            document.getElementById('modal').style.display = 'flex';
        }

        async function runStep1() {
            const phone = document.getElementById('phone').value;
            document.getElementById('btn1').disabled = true;
            log("Sending OTP...");
            try {
                const res = await fetch('/api/send-otp', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({phone})
                });
                const data = await res.json();
                if(data.status === 'success') {
                    sessionId = data.session_id;
                    log("OTP Sent! ID: " + sessionId.substring(0,10)+"...");
                    document.getElementById('step1').style.display = 'none';
                    document.getElementById('step2').style.display = 'block';
                } else {
                    log("Error: " + data.message);
                    document.getElementById('btn1').disabled = false;
                }
            } catch(e) { log(e); }
        }

        async function runStep2() {
            const otp = document.getElementById('otp').value;
            document.getElementById('btn2').disabled = true;
            document.getElementById('gallery').innerHTML = ""; // Clear old images
            log("Verifying... Please wait for screenshots...");
            
            try {
                const res = await fetch('/api/verify-otp', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({otp, session_id: sessionId})
                });
                const data = await res.json();
                
                // Show screenshots immediately
                if(data.screenshots) {
                    data.screenshots.forEach(s => addImage(s.img, s.label));
                }

                if(data.status === 'success') {
                    authData = data.auth_data;
                    log("LOGIN SUCCESSFUL! Keys Found.");
                    document.getElementById('step2').style.display = 'none';
                    document.getElementById('step3').style.display = 'block';
                } else {
                    log("Login Failed: " + data.message);
                    document.getElementById('btn2').disabled = false;
                }
            } catch(e) { log(e); }
        }
        
        async function runStep3() {
            // ... (Same upload logic as before) ...
            const file = document.getElementById('fileInput').files[0];
            const formData = new FormData();
            formData.append("file", file);
            formData.append("cookies_json", JSON.stringify(authData));
            log("Uploading...");
            const res = await fetch('/api/upload', { method: 'POST', body: formData });
            const data = await res.json();
            if(data.status==='success') log("Link: " + data.jazz_link);
            else log("Error: " + data.message);
        }
    </script>
</body>
</html>
"""

# --- Backend Logic ---

@app.get("/")
def home():
    return HTMLResponse(HTML_TEMPLATE)

@app.post("/api/send-otp")
async def send_otp_api(req: NumberRequest):
    # ... (Step 1 is same as before, no changes needed here) ...
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
async def verify_otp_api(req: OtpRequest):
    """
    Step 2 with SCREENSHOT CAPTURE MODE
    """
    screenshots = [] # Store base64 images here
    cookies_dict = {}
    found_key = False
    
    # Helper to capture screenshot
    async def capture(page, label):
        try:
            # Take screenshot buffer
            screenshot_bytes = await page.screenshot(type='png')
            # Convert to base64
            b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            screenshots.append({"label": label, "img": b64})
            print(f"Captured: {label}")
        except Exception as e:
            print(f"Screenshot Error: {e}")

    try:
        async with async_playwright() as p:
            print("Launching Browser...")
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            context = await browser.new_context(user_agent=HEADERS["User-Agent"])
            page = await context.new_page()

            # 1. Open Verify Page
            verify_url = f"https://jazzdrive.com.pk/verify.php?id={req.session_id}"
            await page.goto(verify_url, timeout=60000)
            await capture(page, "1. Verify Page Loaded")

            # 2. Type OTP
            try:
                await page.fill('input[name="otp"]', req.otp)
                await capture(page, "2. OTP Typed")
                
                # Press Enter
                await page.keyboard.press('Enter')
                # Wait a bit to see result of click
                await asyncio.sleep(3)
                await capture(page, "3. After Enter Key")
            except Exception as e:
                await capture(page, f"Error Typing: {str(e)}")

            # 3. Wait for Redirect (Cloud Dashboard)
            try:
                # 30 سیکنڈ کا انتظار کریں گے
                await page.wait_for_url("https://cloud.jazzdrive.com.pk/**", timeout=30000)
                await asyncio.sleep(5) # ڈیش بورڈ کو پورا لوڈ ہونے دیں
                await capture(page, "4. Dashboard/Final Page")
                
                print(f"Landed on: {page.url}")
            except Exception as e:
                await capture(page, "4. Timeout/Stuck Here")
                print(f"Wait Timeout: {e}")

            # 4. Extract Cookies/Key
            cookies = await context.cookies()
            for c in cookies:
                cookies_dict[c['name']] = c['value']
            
            # URL Scan for Key
            if "validationkey=" in page.url.lower():
                from urllib.parse import urlparse, parse_qs
                parsed = parse_qs(urlparse(page.url).query)
                for k, v in parsed.items():
                    if k.lower() == 'validationkey':
                        cookies_dict['validationKey'] = v[0]
                        found_key = True
            
            # Cookie Scan for Key
            if not found_key:
                for k, v in cookies_dict.items():
                    if k.lower() == 'validationkey':
                        found_key = True

            await browser.close()

        # Result Logic
        if found_key:
            return {
                "status": "success", 
                "auth_data": cookies_dict, 
                "screenshots": screenshots # Return images to frontend
            }
        else:
            return {
                "status": "fail", 
                "message": "Key not found. Check screenshots for errors.", 
                "debug": str(cookies_dict),
                "screenshots": screenshots
            }

    except Exception as e:
        return {"status": "error", "message": str(e), "screenshots": screenshots}

@app.post("/api/upload")
async def upload_file_api(file: UploadFile = File(...), cookies_json: str = Form(...)):
    # ... (Same Upload logic as provided in previous turns) ...
    # جگہ بچانے کے لیے کوڈ دوبارہ نہیں لکھ رہا، پچھلا والا ہی استعمال کریں
    try:
        cookies = json.loads(cookies_json)
        v_key = cookies.get('validationKey') or cookies.get('validationkey')
        if not v_key: return {"status":"fail", "message":"Missing Key"}
        
        # ... (Rest of upload logic) ...
        # (For testing just return dummy success if you want to test UI, 
        # but better keep original logic)
        return {"status": "fail", "message": "Add Upload Code Here"} 
    except: return {"status":"error"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
