import os
import uvicorn
import requests
import json
import asyncio
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from playwright.async_api import async_playwright

app = FastAPI()

# --- Global Constants ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://cloud.jazzdrive.com.pk",
    "Referer": "https://cloud.jazzdrive.com.pk/"
}

# --- Data Models ---
class NumberRequest(BaseModel):
    phone: str

class OtpRequest(BaseModel):
    otp: str
    session_id: str

# --- 1. فرنٹ اینڈ (HTML UI) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Jazz Drive Bot Panel</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }
        .container { max-width: 600px; margin: 0 auto; background: #1e293b; padding: 25px; border-radius: 12px; border: 1px solid #334155; }
        h2 { color: #38bdf8; border-bottom: 1px solid #334155; padding-bottom: 15px; }
        input, button { width: 100%; padding: 12px; margin: 8px 0; border-radius: 6px; border: 1px solid #475569; box-sizing: border-box; }
        input { background: #0f172a; color: white; }
        button { background: #0ea5e9; color: white; font-weight: bold; cursor: pointer; border: none; }
        button:hover { background: #0284c7; }
        button:disabled { background: #475569; cursor: not-allowed; }
        .hidden { display: none; }
        #logs { margin-top: 20px; background: #000; padding: 15px; height: 200px; overflow-y: auto; font-family: monospace; font-size: 12px; color: #4ade80; border-radius: 6px; }
        .link-box { background: #064e3b; padding: 10px; margin-top: 10px; border-radius: 6px; word-break: break-all; }
        a { color: #4ade80; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🚀 Jazz Drive Bot Manager</h2>
        
        <div id="step1">
            <label>Phone Number:</label>
            <input type="text" id="phone" placeholder="030xxxxxxxxx" value="03027665767">
            <button onclick="sendOtp()" id="btn1">Send OTP</button>
        </div>

        <div id="step2" class="hidden">
            <label>Enter OTP Code:</label>
            <input type="text" id="otp" placeholder="1234">
            <button onclick="verifyOtp()" id="btn2">Verify & Login</button>
        </div>

        <div id="step3" class="hidden">
            <h3 style="color: #4ade80;">✅ Login Active</h3>
            <label>Upload File to Get Link:</label>
            <input type="file" id="fileInput">
            <button onclick="uploadFile()" id="btn3">Upload & Generate Link</button>
            <div id="resultArea" class="hidden"></div>
        </div>

        <div id="logs">System Ready...</div>
    </div>

    <script>
        let sessionId = "";
        let authCookies = null;

        function log(msg) {
            const l = document.getElementById('logs');
            l.innerHTML += `<div>> ${msg}</div>`;
            l.scrollTop = l.scrollHeight;
        }

        async function sendOtp() {
            const phone = document.getElementById('phone').value;
            document.getElementById('btn1').disabled = true;
            log("Extracting ID and Sending OTP...");
            
            try {
                const res = await fetch('/api/send-otp', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({phone})
                });
                const data = await res.json();
                
                if(data.status === 'success') {
                    sessionId = data.session_id;
                    log("OTP Sent! ID: " + sessionId);
                    document.getElementById('step1').classList.add('hidden');
                    document.getElementById('step2').classList.remove('hidden');
                } else {
                    log("Error: " + data.message);
                    document.getElementById('btn1').disabled = false;
                }
            } catch(e) { log("Error: " + e); }
        }

        async function verifyOtp() {
            const otp = document.getElementById('otp').value;
            document.getElementById('btn2').disabled = true;
            log("Verifying OTP & Fetching Cookies (This uses Browser)...");
            
            try {
                const res = await fetch('/api/verify-otp', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({otp, session_id: sessionId})
                });
                const data = await res.json();
                
                if(data.status === 'success') {
                    authCookies = data.auth_data;
                    log("Login Successful! Cookies Saved.");
                    document.getElementById('step2').classList.add('hidden');
                    document.getElementById('step3').classList.remove('hidden');
                } else {
                    log("Login Failed: " + data.message);
                    document.getElementById('btn2').disabled = false;
                }
            } catch(e) { log("Error: " + e); }
        }

        async function uploadFile() {
            const file = document.getElementById('fileInput').files[0];
            if(!file) return alert("Select a file");
            
            document.getElementById('btn3').disabled = true;
            log(`Uploading ${file.name}... Please wait...`);
            
            const formData = new FormData();
            formData.append("file", file);
            formData.append("cookies_json", JSON.stringify(authCookies));

            try {
                const res = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                
                if(data.status === 'success') {
                    log("File Uploaded! ID: " + data.file_id);
                    const html = `<div class="link-box">
                        <b>Direct Link:</b><br>
                        <a href="${data.jazz_link}" target="_blank">${data.jazz_link}</a>
                    </div>`;
                    document.getElementById('resultArea').innerHTML = html;
                    document.getElementById('resultArea').classList.remove('hidden');
                } else {
                    log("Upload Failed: " + data.message);
                }
            } catch(e) { log("Network Error: " + e); }
            document.getElementById('btn3').disabled = false;
        }
    </script>
</body>
</html>
"""

# --- 2. Backend Logic ---

@app.get("/")
def home():
    return HTMLResponse(HTML_TEMPLATE)

@app.post("/api/send-otp")
async def send_otp_api(req: NumberRequest):
    """بیک گراؤنڈ براؤزر کے ذریعے ID نکال کر OTP بھیجتا ہے"""
    session_id = None
    try:
        async with async_playwright() as p:
            # براؤزر لانچ (ریلوے کے لیے args ضروری ہیں)
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            context = await browser.new_context(user_agent=HEADERS["User-Agent"])
            page = await context.new_page()
            
            try:
                # 1. کلاؤڈ پیج کھولیں تاکہ ID جنریٹ ہو
                await page.goto("https://cloud.jazzdrive.com.pk", timeout=60000)
                
                # 2. ری ڈائریکٹ کا انتظار کریں (signup.php یا verify.php)
                # ہم انتظار کریں گے کہ URL میں 'id=' آ جائے
                await page.wait_for_url("**id=*", timeout=60000)
                
                final_url = page.url
                if "id=" in final_url:
                    session_id = final_url.split("id=")[1].split("&")[0]
            except Exception as e:
                print(f"Browser Error: {e}")
            finally:
                await browser.close()

        if not session_id:
            return {"status": "fail", "message": "Could not extract Session ID from Jazz Drive"}

        # 3. اب API کے ذریعے نمبر بھیجیں (یہ تیز ہے)
        otp_url = f"https://jazzdrive.com.pk/oauth2/signup.php?id={session_id}"
        payload = {"msisdn": req.phone, "enrichment_status": ""}
        
        # Requests (Sync) call inside Async using run_in_executor usually, but strictly here for simplicity
        resp = requests.post(otp_url, data=payload, headers=HEADERS)
        
        if resp.status_code in [200, 302]:
            return {"status": "success", "session_id": session_id}
        else:
            return {"status": "fail", "message": "Jazz rejected the number", "debug": resp.text}

    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/verify-otp")
async def verify_otp_api(req: OtpRequest):
    """
    یہ سب سے اہم حصہ ہے۔
    ہم براؤزر استعمال کریں گے تاکہ 'verify.php' -> 'authorize.php' -> 'oauth.html'
    کا پورا چکر چلے اور ہمیں 'validationKey' ملے۔
    """
    cookies_dict = {}
    validation_key = None
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            context = await browser.new_context(user_agent=HEADERS["User-Agent"])
            page = await context.new_page()

            # 1. Verify Page پر جائیں (یہ GET ریکوسٹ فارم کھولے گی)
            # URL: https://jazzdrive.com.pk/verify.php?id=...
            verify_page_url = f"https://jazzdrive.com.pk/verify.php?id={req.session_id}"
            
            print(f"Navigating to Verify Page: {verify_page_url}")
            await page.goto(verify_page_url, timeout=60000)
            
            # 2. OTP ٹائپ کریں
            # اکثر OTP فیلڈ کا نام 'otp' ہوتا ہے
            try:
                await page.fill('input[name="otp"]', req.otp)
                # Submit بٹن دبائیں (یا Enter)
                await page.press('input[name="otp"]', 'Enter')
            except:
                # اگر Enter کام نہ کرے تو بٹن ڈھونڈیں
                await page.click('button[type="submit"]')

            print("OTP Submitted. Waiting for Cloud Dashboard...")

            # 3. Cloud Dashboard پر لینڈ کرنے کا انتظار کریں
            # جب لاگ ان ہو جائے گا تو URL 'cloud.jazzdrive.com.pk' ہو جائے گا
            try:
                await page.wait_for_url("https://cloud.jazzdrive.com.pk/**", timeout=60000)
                print("Landed on Cloud Dashboard!")
            except:
                # اگر ٹائم آؤٹ ہو جائے تو شاید لاگ ان فیل ہوا
                await browser.close()
                return {"status": "fail", "message": "Login Timeout or Wrong OTP"}

            # 4. کوکیز اور Validation Key نکالیں
            # کوکیز براؤزر سے حاصل کریں
            cookies = await context.cookies()
            for cookie in cookies:
                cookies_dict[cookie['name']] = cookie['value']
                # validationKey اکثر کوکی میں بھی ہوتی ہے
                if cookie['name'].lower() == 'validationkey':
                    validation_key = cookie['value']
            
            # اگر validationKey کوکی میں نہیں ملی تو URL سے نکالیں
            # URL: ...&validationkey=XYZ...
            current_url = page.url
            if "validationkey=" in current_url.lower():
                # URL parsing logic
                from urllib.parse import urlparse, parse_qs
                parsed = parse_qs(urlparse(current_url).query)
                # یہ case-insensitive ڈھونڈنے کی کوشش
                for key in parsed:
                    if key.lower() == 'validationkey':
                        validation_key = parsed[key][0]
                        cookies_dict['validationKey'] = validation_key # اسے کوکیز میں بھی ڈال دیں

            await browser.close()

    except Exception as e:
        return {"status": "error", "message": str(e)}

    # چیک کریں کہ لاگ ان ڈیٹا ملا یا نہیں
    if not cookies_dict.get('JSESSIONID') and not validation_key:
        return {"status": "fail", "message": "Login processed but no session found. Try again."}

    # کامیابی!
    return {
        "status": "success",
        "auth_data": cookies_dict
    }

@app.post("/api/upload")
async def upload_file_api(
    file: UploadFile = File(...),
    cookies_json: str = Form(...)
):
    """فائل اپ لوڈ اور ڈائریکٹ لنک جنریشن"""
    try:
        cookies = json.loads(cookies_json)
        
        # Validation Key لازمی ہے
        # ہم اسے کوکیز سے نکالیں گے (ہم نے پچھلے سٹیپ میں اسے کوکیز میں ڈال دیا تھا)
        v_key = cookies.get('validationKey') or cookies.get('validationkey')
        
        if not v_key:
            return {"status": "fail", "message": "Validation Key missing in saved cookies."}

        # --- STEP A: Upload Request ---
        # HAR Reference: 
        upload_url = "https://cloud.jazzdrive.com.pk/sapi/upload"
        
        params = {
            "action": "save",
            "acceptasynchronous": "true",
            "validationkey": v_key
        }
        
        # فائل کا ڈیٹا پڑھیں
        file_content = await file.read()
        
        # Multipart Payload
        # HAR میں: name="data" ایک JSON سٹرنگ ہے، اور name="file" فائل ہے۔
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%SZ")
        
        data_field = {
            "data": {
                "name": file.filename,
                "size": len(file_content),
                "modificationdate": timestamp,
                "contenttype": file.content_type or "application/octet-stream"
            }
        }
        
        files_payload = {
            'data': (None, json.dumps(data_field), 'application/json'),
            'file': (file.filename, file_content, file.content_type)
        }
        
        # Requests Session
        session = requests.Session()
        # تمام کوکیز سیٹ کریں
        session.cookies.update(cookies)
        
        print(f"Uploading {file.filename}...")
        resp = session.post(upload_url, params=params, files=files_payload, headers={"User-Agent": HEADERS["User-Agent"]})
        
        if resp.status_code != 200:
            return {"status": "fail", "message": "Upload Failed", "debug": resp.text}
            
        upload_resp = resp.json()
        if "id" not in upload_resp:
             return {"status": "fail", "message": "Upload success but no ID returned", "debug": str(upload_resp)}
             
        file_id = upload_resp["id"]
        print(f"Uploaded. File ID: {file_id}")

        # --- STEP B: Get Direct Link ---
        # HAR Reference: 
        link_url = "https://cloud.jazzdrive.com.pk/sapi/media"
        link_params = {
            "action": "get",
            "origin": "omh,dropbox",
            "validationkey": v_key
        }
        
        # Payload
        link_payload = {
            "data": {
                "ids": [file_id], # نوٹ: یہ سٹرنگ یا انٹجر ہو سکتا ہے، JSON میں اکثر انٹجر جاتا ہے
                "fields": ["url", "name", "size"]
            }
        }
        
        # یہ JSON ہے
        resp_link = session.post(link_url, params=link_params, json=link_payload, headers=HEADERS)
        link_data = resp_link.json()
        
        direct_url = None
        if "data" in link_data and "media" in link_data["data"]:
            media_list = link_data["data"]["media"]
            if len(media_list) > 0:
                direct_url = media_list[0].get("url")
        
        if direct_url:
            return {
                "status": "success",
                "file_id": file_id,
                "jazz_link": direct_url
            }
        else:
            return {"status": "fail", "message": "Link not found in response", "debug": str(link_data)}

    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
