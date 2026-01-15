import os
import uvicorn
import requests
import json
import asyncio
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from playwright.async_api import async_playwright

app = FastAPI()

# --- Global Config ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://jazzdrive.com.pk",
    "Referer": "https://jazzdrive.com.pk/"
}

# --- Data Models ---
class NumberRequest(BaseModel):
    phone: str

class OtpRequest(BaseModel):
    otp: str
    session_id: str

# --- 1. Frontend UI (Dark Terminal Theme) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Jazz Drive Bot Debugger</title>
    <style>
        body { background-color: #0d1117; color: #c9d1d9; font-family: 'Courier New', monospace; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; }
        h2 { border-bottom: 1px solid #30363d; padding-bottom: 10px; color: #58a6ff; }
        
        .panel { background: #161b22; border: 1px solid #30363d; padding: 20px; border-radius: 6px; margin-bottom: 20px; }
        
        input { background: #0d1117; border: 1px solid #30363d; color: #fff; padding: 10px; width: 60%; border-radius: 4px; }
        button { background: #238636; color: white; border: none; padding: 10px 20px; cursor: pointer; border-radius: 4px; font-weight: bold; }
        button:disabled { background: #30363d; cursor: not-allowed; }
        
        #console { 
            background: #000; border: 1px solid #333; height: 400px; 
            overflow-y: scroll; padding: 15px; font-size: 13px; white-space: pre-wrap;
            color: #0f0; border-radius: 4px;
        }
        .log-info { color: #8b949e; }
        .log-success { color: #3fb950; }
        .log-warn { color: #d29922; }
        .log-error { color: #f85149; }
        .hidden { display: none; }
        a { color: #58a6ff; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🛠️ Jazz Drive API Terminal</h2>
        
        <div class="panel">
            <div id="step1">
                <p>1. Enter User Phone Number:</p>
                <input type="text" id="phone" value="03027665767">
                <button onclick="runStep1()" id="btn1">Send OTP</button>
            </div>

            <div id="step2" class="hidden">
                <p>2. Enter OTP Code:</p>
                <input type="text" id="otp" placeholder="e.g. 1234">
                <button onclick="runStep2()" id="btn2">Verify (API)</button>
            </div>

            <div id="step3" class="hidden">
                <p>3. Upload File (Get Direct Link):</p>
                <input type="file" id="fileInput">
                <button onclick="runStep3()" id="btn3">Upload File</button>
            </div>
        </div>

        <h3>📟 Live Console Logs:</h3>
        <div id="console">System Ready... Waiting for commands.</div>
    </div>

    <script>
        let sessionId = "";
        let authData = null;

        function log(msg, type="info") {
            const c = document.getElementById('console');
            const time = new Date().toLocaleTimeString();
            let color = "log-info";
            if(type==="success") color = "log-success";
            if(type==="error") color = "log-error";
            if(type==="warn") color = "log-warn";
            
            c.innerHTML += `<div class="${color}">[${time}] ${msg}</div>`;
            c.scrollTop = c.scrollHeight;
        }

        async function runStep1() {
            const phone = document.getElementById('phone').value;
            document.getElementById('btn1').disabled = true;
            log("🚀 Starting Sequence for " + phone + "...", "warn");
            
            try {
                const res = await fetch('/api/send-otp', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({phone})
                });
                const data = await res.json();
                
                if(data.status === 'success') {
                    sessionId = data.session_id;
                    log("✅ Signup ID Captured: " + sessionId.substring(0,15)+"...", "success");
                    log("📤 OTP Sent successfully via API.", "success");
                    document.getElementById('step1').classList.add('hidden');
                    document.getElementById('step2').classList.remove('hidden');
                } else {
                    log("❌ Failed: " + data.message, "error");
                    if(data.debug) log("Debug: " + data.debug, "error");
                    document.getElementById('btn1').disabled = false;
                }
            } catch(e) { log("Error: " + e, "error"); }
        }

        async function runStep2() {
            const otp = document.getElementById('otp').value;
            document.getElementById('btn2').disabled = true;
            log("⏳ Verifying OTP via API (No Browser Click)...", "warn");
            
            try {
                const res = await fetch('/api/verify-otp', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({otp, session_id: sessionId})
                });
                const data = await res.json();
                
                if(data.status === 'success') {
                    authData = data.auth_data;
                    log("🎉 LOGIN SUCCESSFUL!", "success");
                    log("🍪 Validation Key: " + (authData.validationKey || "FOUND"), "success");
                    document.getElementById('step2').classList.add('hidden');
                    document.getElementById('step3').classList.remove('hidden');
                } else {
                    log("❌ Login Failed: " + data.message, "error");
                    if(data.debug) log("Debug: " + data.debug, "info");
                    document.getElementById('btn2').disabled = false;
                }
            } catch(e) { log("Error: " + e, "error"); }
        }

        async function runStep3() {
            const file = document.getElementById('fileInput').files[0];
            if(!file) return alert("Select file");
            
            document.getElementById('btn3').disabled = true;
            log(`📤 Uploading ${file.name} to Jazz Drive...`, "warn");
            
            const formData = new FormData();
            formData.append("file", file);
            formData.append("cookies_json", JSON.stringify(authData));

            try {
                const res = await fetch('/api/upload', { method: 'POST', body: formData });
                const data = await res.json();
                
                if(data.status === 'success') {
                    log("✅ Upload Complete! ID: " + data.file_id, "success");
                    log("🔗 GENERATED LINK: " + data.jazz_link, "success");
                    
                    // Show Link clearly
                    const linkDiv = document.createElement("div");
                    linkDiv.style = "background:#238636;color:white;padding:10px;margin-top:10px;border-radius:4px;";
                    linkDiv.innerHTML = `<b>Final Link:</b> <a href="${data.jazz_link}" target="_blank" style="color:white;">${data.jazz_link}</a>`;
                    document.getElementById('console').appendChild(linkDiv);
                } else {
                    log("❌ Upload Error: " + data.message, "error");
                    if(data.debug) log("Debug: " + data.debug, "info");
                }
            } catch(e) { log("Error: " + e, "error"); }
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
    """
    Step 1: Get ID via Playwright (Background) -> Send OTP via API
    """
    session_id = None
    try:
        print(f"--- [Step 1] Processing Number: {req.phone} ---")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = await browser.new_page(user_agent=HEADERS["User-Agent"])
            
            try:
                print("browser: Opening cloud.jazzdrive.com.pk...")
                await page.goto("https://cloud.jazzdrive.com.pk", timeout=60000)
                
                print("browser: Waiting for ID in URL...")
                # ہم کسی بھی ری ڈائریکٹ کا انتظار کریں گے جس میں ID ہو
                await page.wait_for_url("**id=*", timeout=60000)
                
                final_url = page.url
                print(f"browser: Landed on {final_url}")
                
                if "id=" in final_url:
                    session_id = final_url.split("id=")[1].split("&")[0]
            except Exception as e:
                print(f"Browser Error: {e}")
            finally:
                await browser.close()

        if not session_id:
            return {"status": "fail", "message": "Could not extract Signup ID"}

        # API Call
        print(f"API: Sending OTP to {req.phone} with ID {session_id}")
        resp = requests.post(
            f"https://jazzdrive.com.pk/oauth2/signup.php?id={session_id}",
            data={"msisdn": req.phone, "enrichment_status": ""},
            headers=HEADERS
        )
        
        if resp.status_code in [200, 302]:
            return {"status": "success", "session_id": session_id}
        else:
            return {"status": "fail", "message": "Jazz API rejected number", "debug": resp.text[:200]}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/verify-otp")
async def verify_otp_api(req: OtpRequest):
    """
    Step 2: Verify OTP via API (NO CLICKING) -> Follow Redirect via Browser -> Get Cookies
    """
    try:
        print(f"--- [Step 2] Verifying OTP: {req.otp} ---")
        
        # 1. API Verification (No Browser Click)
        verify_url = f"https://jazzdrive.com.pk/verify.php?id={req.session_id}"
        session = requests.Session()
        
        print(f"API: POST to {verify_url}")
        # allow_redirects=False تاکہ ہم 302 پکڑ سکیں
        resp = session.post(verify_url, data={"otp": req.otp}, headers=HEADERS, allow_redirects=False)
        
        target_url = ""
        
        if resp.status_code == 302:
            target_url = resp.headers.get("Location")
            print(f"API: OTP Accepted! Redirecting to: {target_url}")
        else:
            # کبھی کبھی 200 آتا ہے اگر OTP غلط ہو
            return {"status": "fail", "message": f"Invalid OTP (Status {resp.status_code})", "debug": resp.text[:200]}
            
        if not target_url:
             return {"status": "fail", "message": "No redirect URL found after verification"}

        # 2. Browser Follow-up (Passive)
        # اب ہم براؤزر کو صرف کہیں گے کہ اس لنک پر جاؤ (authorize.php) اور جو بھی آگے ہو اسے ہونے دو
        cookies_dict = {}
        
        print("browser: Launching to follow redirect chain...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(user_agent=HEADERS["User-Agent"])
            page = await context.new_page()

            try:
                # اگر URL ریلیٹو (Relative) ہے تو پورا کریں
                if target_url.startswith("/"):
                    target_url = "https://jazzdrive.com.pk" + target_url
                
                print(f"browser: Going to {target_url}")
                await page.goto(target_url, timeout=60000)
                
                print("browser: Waiting for Cloud Dashboard...")
                # کامیاب لاگ ان پر یہ cloud.jazzdrive.com.pk پر جائے گا
                await page.wait_for_url("https://cloud.jazzdrive.com.pk/**", timeout=60000)
                print(f"browser: Reached {page.url}")
                
                # کوکیز اٹھائیں
                cookies = await context.cookies()
                for c in cookies:
                    cookies_dict[c['name']] = c['value']
                
                # Validation Key URL سے نکالیں (Backup)
                if "validationkey=" in page.url.lower():
                    from urllib.parse import urlparse, parse_qs
                    parsed = parse_qs(urlparse(page.url).query)
                    # Case-insensitive search
                    for k, v in parsed.items():
                        if k.lower() == 'validationkey':
                            cookies_dict['validationKey'] = v[0]

            except Exception as e:
                print(f"Browser Error during redirect: {e}")
            finally:
                await browser.close()

        # Check Results
        # یا تو JSESSIONID ہو یا validationKey
        v_key = cookies_dict.get('validationKey') or cookies_dict.get('validationkey')
        
        if v_key:
            print(f"SUCCESS: Found Validation Key: {v_key}")
            return {"status": "success", "auth_data": cookies_dict}
        else:
            print("FAIL: Login seemed successful but Cookies/Keys missing.")
            return {"status": "fail", "message": "Login OK but failed to capture Keys", "debug": str(cookies_dict)}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/upload")
async def upload_file_api(file: UploadFile = File(...), cookies_json: str = Form(...)):
    """
    Step 3: Upload using extracted Validation Key
    """
    try:
        print(f"--- [Step 3] Uploading File: {file.filename} ---")
        cookies = json.loads(cookies_json)
        v_key = cookies.get('validationKey') or cookies.get('validationkey')
        
        if not v_key:
            return {"status": "fail", "message": "Validation Key not found. Please Login again."}

        # Setup Upload
        upload_url = "https://cloud.jazzdrive.com.pk/sapi/upload"
        params = {"action": "save", "acceptasynchronous": "true", "validationkey": v_key}
        
        # Prepare Data
        file_content = await file.read()
        import datetime
        ts = datetime.datetime.now().strftime("%Y%m%dT%H%M%SZ")
        
        json_meta = {
            "data": {
                "name": file.filename,
                "size": len(file_content),
                "modificationdate": ts,
                "contenttype": file.content_type or "application/octet-stream"
            }
        }
        
        files = {
            'data': (None, json.dumps(json_meta), 'application/json'),
            'file': (file.filename, file_content, file.content_type)
        }
        
        session = requests.Session()
        session.cookies.update(cookies)
        
        print("API: Posting file...")
        resp = session.post(upload_url, params=params, files=files, headers={"User-Agent": HEADERS["User-Agent"]})
        
        if resp.status_code != 200:
            return {"status": "fail", "message": "Upload Error", "debug": resp.text}
            
        data = resp.json()
        if "id" not in data:
             return {"status": "fail", "message": "No File ID returned", "debug": str(data)}
             
        file_id = data["id"]
        print(f"Upload Success! ID: {file_id}")
        
        # Get Link
        link_url = "https://cloud.jazzdrive.com.pk/sapi/media"
        link_payload = {"data": {"ids": [file_id], "fields": ["url"]}}
        
        resp_link = session.post(
            link_url, 
            params={"action": "get", "origin": "omh,dropbox", "validationkey": v_key},
            json=link_payload,
            headers={"User-Agent": HEADERS["User-Agent"]}
        )
        
        link_data = resp_link.json()
        final_url = link_data.get("data", {}).get("media", [{}])[0].get("url")
        
        if final_url:
            return {"status": "success", "file_id": file_id, "jazz_link": final_url}
        else:
            return {"status": "fail", "message": "Could not generate link", "debug": str(link_data)}

    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
