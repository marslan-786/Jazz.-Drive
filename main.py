import os
import uvicorn
import requests
import json
from urllib.parse import urlparse, parse_qs
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from playwright.sync_api import sync_playwright

app = FastAPI()

# --- Database for Logs ---
logs_db = {}

# --- Browser-Like Headers for API Steps ---
API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1"
}

# --- Data Models ---
class PhoneRequest(BaseModel):
    phone: str
    session_id: str

class VerifyRequest(BaseModel):
    otp: str
    session_id: str
    verify_url: str
    cookies: dict # کوکیز جو پہلے سٹیپ سے ملیں گی

# --- HTML UI ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ur" dir="rtl">
<head>
    <title>Jazz Drive Hybrid Login</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { background-color: #0d1117; color: #c9d1d9; font-family: monospace; padding: 20px; direction: ltr; }
        .container { max-width: 900px; margin: 0 auto; }
        .input-box { background: #161b22; padding: 20px; border: 1px solid #30363d; border-radius: 6px; margin-bottom: 20px; }
        input { background: #0d1117; border: 1px solid #30363d; color: #fff; padding: 10px; width: 60%; }
        button { background: #238636; color: white; border: none; padding: 10px 20px; cursor: pointer; font-weight: bold; }
        #terminal { background: #000; border: 2px solid #3fb950; height: 500px; overflow-y: scroll; padding: 15px; font-size: 12px; color: #0f0; white-space: pre-wrap; font-family: 'Courier New', monospace; }
        .req-head { color: #58a6ff; font-weight: bold; }
        .res-head { color: #d29922; font-weight: bold; }
        .divider { border-bottom: 1px dashed #30363d; margin: 10px 0; }
        .hidden { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🌐 Jazz Drive Hybrid (Browser + API)</h2>
        
        <div id="step1" class="input-box">
            <p style="color:white">1. نمبر درج کریں (Browser will Fetch ID):</p>
            <input type="text" id="phone" value="03027665767">
            <button onclick="startProcess()">Start Flow</button>
        </div>

        <div id="step2" class="input-box hidden">
            <p style="color:white">2. OTP درج کریں (API verification):</p>
            <input type="text" id="otp" placeholder="1234">
            <button onclick="verifyProcess()">Verify Login</button>
        </div>

        <div style="margin-bottom: 5px; text-align: right;">
            <button onclick="copyLogs()" style="background: #1f6feb;">Copy Logs</button>
        </div>
        
        <div id="terminal">System Ready...</div>
    </div>

    <script>
        let sessionKey = "sess_" + Date.now();
        let pollInterval = null;
        let verifyUrl = "";
        let sessionCookies = {};

        async function startProcess() {
            const phone = document.getElementById('phone').value;
            document.getElementById('step1').querySelector('button').disabled = true;
            document.getElementById('terminal').innerHTML = "Initializing Browser for Session Warmup...";
            
            startPolling();

            try {
                const res = await fetch('/api/start-flow', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({phone: phone, session_id: sessionKey})
                });
                const data = await res.json();
                
                if(data.status === 'success') {
                    verifyUrl = data.verify_url;
                    sessionCookies = data.cookies; // اہم: کوکیز محفوظ کر لیں
                    document.getElementById('step1').classList.add('hidden');
                    document.getElementById('step2').classList.remove('hidden');
                } else {
                    alert("Failed: " + data.message);
                    document.getElementById('step1').querySelector('button').disabled = false;
                }
            } catch(e) { alert("Error: " + e); }
        }

        async function verifyProcess() {
            const otp = document.getElementById('otp').value;
            document.getElementById('step2').querySelector('button').disabled = true;

            try {
                await fetch('/api/verify-otp', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        otp: otp, 
                        session_id: sessionKey, 
                        verify_url: verifyUrl,
                        cookies: sessionCookies
                    })
                });
            } catch(e) { alert("Error: " + e); }
        }

        function startPolling() {
            if(pollInterval) clearInterval(pollInterval);
            pollInterval = setInterval(async () => {
                try {
                    const res = await fetch('/api/get-logs?id=' + sessionKey);
                    const data = await res.json();
                    if(data.logs) {
                        const term = document.getElementById('terminal');
                        term.innerHTML = data.logs;
                        term.scrollTop = term.scrollHeight;
                    }
                } catch(e) {}
            }, 1000);
        }

        function copyLogs() {
            navigator.clipboard.writeText(document.getElementById('terminal').innerText);
            alert("Copied!");
        }
    </script>
</body>
</html>
"""

@app.get("/")
def home(): return HTMLResponse(HTML_TEMPLATE)

def log(session_id, title, req_url, method, info_text):
    if session_id not in logs_db: logs_db[session_id] = ""
    entry = f"""
<div class="divider"></div>
<div class="info">🔹 <b>STEP: {title}</b></div>
<div class="req-head">➡️ {method} {req_url}</div>
<div class="info">{info_text}</div>
"""
    logs_db[session_id] += entry

# --- HYBRID LOGIC ---

@app.post("/api/start-flow")
def start_flow(data: PhoneRequest):
    s_id = data.session_id
    browser_cookies = {}
    signup_url = None
    
    try:
        # 1. BROWSER STEP: Open Cloud Link & Get ID
        log(s_id, "1. Launching Browser", "https://cloud.jazzdrive.com.pk", "BROWSER", "Waiting for redirection to signup.php...")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(user_agent=API_HEADERS["User-Agent"])
            page = context.new_page()
            
            # کلاؤڈ لنک کھولیں
            page.goto("https://cloud.jazzdrive.com.pk", timeout=60000)
            
            # انتظار کریں کہ وہ signup.php پر لے جائے
            try:
                page.wait_for_url("**signup.php**", timeout=45000)
                signup_url = page.url
                log(s_id, "1. Browser Success", signup_url, "INFO", "Landed on Signup Page via Redirect.")
                
                # کوکیز محفوظ کریں (یہ سب سے اہم ہے)
                cookies_list = context.cookies()
                for c in cookies_list:
                    browser_cookies[c['name']] = c['value']
                
                log(s_id, "2. Cookies Extracted", "Internal", "INFO", f"Captured {len(browser_cookies)} cookies from browser session.")
                
            except Exception as e:
                browser.close()
                log(s_id, "ERROR", "Browser Timeout", "FAIL", str(e))
                return {"status": "fail", "message": "Browser failed to reach signup page"}
            
            browser.close()

        # 2. API STEP: Send Phone Number (Using Browser Cookies)
        if not signup_url: return {"status": "fail", "message": "No Signup URL found"}
        
        session = requests.Session()
        # براؤزر والی کوکیز سیشن میں ڈالیں
        session.cookies.update(browser_cookies)
        
        payload = {"enrichment_status": "", "msisdn": data.phone}
        
        # Headers میں Referer بہت ضروری ہے
        headers = API_HEADERS.copy()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Referer"] = signup_url
        headers["Origin"] = "https://jazzdrive.com.pk"
        
        log(s_id, "3. Sending SMS (API)", signup_url, "POST", "Sending number with browser cookies...")
        
        r = session.post(signup_url, data=payload, headers=headers, allow_redirects=False)
        
        log(s_id, "3. SMS Result", str(r.status_code), "INFO", f"Location: {r.headers.get('Location', 'None')}")
        
        if r.status_code == 302 and 'Location' in r.headers:
            verify_url = r.headers['Location']
            # اگر لنک ریلیٹو ہے تو پورا کریں
            if verify_url.startswith("/"):
                verify_url = "https://jazzdrive.com.pk" + verify_url
                
            return {
                "status": "success", 
                "verify_url": verify_url,
                "cookies": session.cookies.get_dict() # اپڈیٹڈ کوکیز واپس بھیجیں
            }
        else:
            return {"status": "fail", "message": "SMS Sending Failed (No Redirect)"}

    except Exception as e:
        log(s_id, "CRITICAL ERROR", str(e), "FAIL", "")
        return {"status": "error", "message": str(e)}

@app.post("/api/verify-otp")
def verify_otp_api(data: VerifyRequest):
    s_id = data.session_id
    try:
        # پچھلے سٹیپ کی کوکیز کے ساتھ سیشن بنائیں
        session = requests.Session()
        session.cookies.update(data.cookies)
        
        # 4. Verify OTP (API)
        headers = API_HEADERS.copy()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Referer"] = data.verify_url
        headers["Origin"] = "https://jazzdrive.com.pk"
        
        log(s_id, "4. Verifying OTP", data.verify_url, "POST", f"Code: {data.otp}")
        
        r4 = session.post(data.verify_url, data={"otp": data.otp}, headers=headers, allow_redirects=False)
        
        log(s_id, "4. Verification Result", str(r4.status_code), "INFO", r4.headers.get('Location', 'No Location'))
        
        if r4.status_code != 302:
            return {"status": "fail", "message": "Invalid OTP"}

        # 5. Follow Redirect Chain to get Tokens
        auth_url = r4.headers['Location']
        if auth_url.startswith("/"): auth_url = "https://jazzdrive.com.pk" + auth_url
        
        log(s_id, "5. Following Redirect", auth_url, "GET", "Getting OAuth Code...")
        r5 = session.get(auth_url, headers=API_HEADERS, allow_redirects=False)
        
        if 'Location' in r5.headers:
            cloud_redirect = r5.headers['Location']
            log(s_id, "6. Cloud Redirect Found", cloud_redirect, "SUCCESS", "Ready to extract login keys.")
            
            # یہاں آپ further login logic لگا سکتے ہیں (جیسا پچھلے کوڈ میں تھا)
            parsed = parse_qs(urlparse(cloud_redirect).query)
            code = parsed.get('code', [None])[0]
            if code:
                 log(s_id, "FINAL", f"OAuth Code: {code}", "SUCCESS", "Use this code to get tokens via /sapi/login/oauth")

        return {"status": "success"}

    except Exception as e:
        log(s_id, "ERROR", str(e), "FAIL", "")
        return {"status": "error", "message": str(e)}

@app.get("/api/get-logs")
def get_logs(id: str): return {"logs": logs_db.get(id, "")}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
