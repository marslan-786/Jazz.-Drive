import os
import uvicorn
import requests
import json
from urllib.parse import urlparse, parse_qs
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI()

# --- Database for Logs ---
logs_db = {}

# --- Browser-Like Headers (تاکہ جیز سمجھے یہ اصلی بندہ ہے) ---
REAL_HEADERS = {
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

class PhoneRequest(BaseModel):
    phone: str
    session_id: str

class VerifyRequest(BaseModel):
    otp: str
    session_id: str
    verify_url: str

# --- HTML UI (Terminal View) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ur" dir="rtl">
<head>
    <title>Jazz Drive Organic Flow</title>
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
        <h2>🌐 Jazz Drive Organic Login</h2>
        
        <div id="step1" class="input-box">
            <p style="color:white">1. نمبر درج کریں:</p>
            <input type="text" id="phone" value="03027665767">
            <button onclick="startProcess()">Start Flow</button>
        </div>

        <div id="step2" class="input-box hidden">
            <p style="color:white">2. OTP درج کریں:</p>
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

        async function startProcess() {
            const phone = document.getElementById('phone').value;
            document.getElementById('step1').querySelector('button').disabled = true;
            document.getElementById('terminal').innerHTML = "Initializing Full Chain...";
            
            startPolling();

            try {
                const res = await fetch('/api/send-otp', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({phone: phone, session_id: sessionKey})
                });
                const data = await res.json();
                
                if(data.status === 'success') {
                    verifyUrl = data.verify_url;
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
                    body: JSON.stringify({otp: otp, session_id: sessionKey, verify_url: verifyUrl})
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

def log(session_id, title, req_url, method, req_headers, req_body, res_status, res_headers, res_body):
    if session_id not in logs_db: logs_db[session_id] = ""
    
    cookies_display = "Cookies Set!" if "Set-Cookie" in res_headers else "No Cookies"
    
    entry = f"""
<div class="divider"></div>
<div class="info">🔹 <b>STEP: {title}</b></div>
<div class="req-head">➡️ {method} {req_url}</div>
<div class="info">Headers: {json.dumps(dict(req_headers), indent=2)}</div>
<div class="res-head">⬅️ STATUS: {res_status} | {cookies_display}</div>
<div class="info">Location: {res_headers.get('Location', 'None')}</div>
"""
    logs_db[session_id] += entry

# --- API LOGIC (ORGANIC FLOW) ---

# گلوبل سیشن (تاکہ کوکیز محفوظ رہیں)
# نوٹ: پروڈکشن میں ہر یوزر کا الگ سیشن ہونا چاہیے، فی الحال ٹیسٹنگ کے لیے یہ کافی ہے۔
global_session = requests.Session()

@app.post("/api/send-otp")
def send_otp_api(data: PhoneRequest):
    s_id = data.session_id
    try:
        # ہر بار نیا سیشن شروع کریں تاکہ پرانی کوکیز مسئلہ نہ کریں
        global global_session
        global_session = requests.Session()
        
        # 1. Start from CLOUD Home Page (The "Origin")
        # یہ سب سے اہم سٹیپ ہے۔ یہاں سے ہمیں پہلی کوکیز ملیں گی۔
        cloud_home = "https://cloud.jazzdrive.com.pk"
        log(s_id, "1. Visiting Cloud Home (Get Cookies)", cloud_home, "GET", REAL_HEADERS, "", "Pending...", {}, "")
        
        r1 = global_session.get(cloud_home, headers=REAL_HEADERS)
        log(s_id, "1. Result", cloud_home, "GET", r1.request.headers, "", r1.status_code, r1.headers, "")

        # 2. It usually redirects to /ui/html/login.html or similar, let's hit Authorize manually now
        # اب چونکہ ہمارے پاس cloud.jazzdrive کی کوکیز ہیں، اب ہم authorize کال کر سکتے ہیں۔
        auth_url = "https://jazzdrive.com.pk/oauth2/authorization.php?response_type=code&client_id=web&state=66551&redirect_uri=https://cloud.jazzdrive.com.pk/ui/html/oauth.html"
        
        # Headers update for redirect
        auth_headers = REAL_HEADERS.copy()
        auth_headers["Referer"] = "https://cloud.jazzdrive.com.pk/"
        
        log(s_id, "2. Requesting Authorization", auth_url, "GET", auth_headers, "", "Pending...", {}, "")
        
        r2 = global_session.get(auth_url, headers=auth_headers, allow_redirects=False)
        log(s_id, "2. Result (Should be 302)", auth_url, "GET", r2.request.headers, "", r2.status_code, r2.headers, "")
        
        if 'Location' not in r2.headers:
            return {"status": "fail", "message": "Authorization did not redirect"}
            
        signup_url = f"https://jazzdrive.com.pk/oauth2/{r2.headers['Location']}"
        
        # 3. Signup Page (Send Phone Number)
        # اب ہم Signup ID کے ساتھ نمبر بھیجیں گے
        post_headers = REAL_HEADERS.copy()
        post_headers["Content-Type"] = "application/x-www-form-urlencoded"
        post_headers["Origin"] = "https://jazzdrive.com.pk"
        post_headers["Referer"] = signup_url # یہ بہت ضروری ہے
        
        payload = {"enrichment_status": "", "msisdn": data.phone}
        
        log(s_id, "3. Sending Phone Number", signup_url, "POST", post_headers, str(payload), "Pending...", {}, "")
        
        r3 = global_session.post(signup_url, data=payload, headers=post_headers, allow_redirects=False)
        log(s_id, "3. Result", signup_url, "POST", r3.request.headers, str(payload), r3.status_code, r3.headers, "")
        
        if 'Location' not in r3.headers:
            return {"status": "fail", "message": "No Redirect after sending phone"}
            
        return {"status": "success", "verify_url": r3.headers['Location']}

    except Exception as e:
        log(s_id, "ERROR", "", "", {}, "", "Error", {}, str(e))
        return {"status": "error", "message": str(e)}

@app.post("/api/verify-otp")
def verify_otp_api(data: VerifyRequest):
    s_id = data.session_id
    try:
        # ہم وہی global_session استعمال کریں گے جس میں کوکیز پڑی ہیں
        
        # 4. Verify OTP
        headers = REAL_HEADERS.copy()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Referer"] = data.verify_url
        headers["Origin"] = "https://jazzdrive.com.pk"
        
        log(s_id, "4. Verifying OTP", data.verify_url, "POST", headers, data.otp, "Pending...", {}, "")
        
        r4 = global_session.post(data.verify_url, data={"otp": data.otp}, headers=headers, allow_redirects=False)
        log(s_id, "4. Result", data.verify_url, "POST", r4.request.headers, "", r4.status_code, r4.headers, "")
        
        if r4.status_code != 302:
            return {"status": "fail", "message": "Invalid OTP or Session Expired"}

        # 5. Follow the redirect chain to get Token
        # (یہاں سے آگے کا کوڈ ویسا ہی ہے جیسا پہلے تھا، بس سیشن وہی یوز ہو رہا ہے)
        next_url = "https://jazzdrive.com.pk" + r4.headers['Location']
        r5 = global_session.get(next_url, headers=REAL_HEADERS, allow_redirects=False)
        
        if 'Location' in r5.headers:
            cloud_redirect = r5.headers['Location']
            log(s_id, "5. Got Cloud Redirect", cloud_redirect, "INFO", {}, "", "", {}, "")
            
            # Extract Code and Login... (Same as before)
            parsed = parse_qs(urlparse(cloud_redirect).query)
            code = parsed.get('code', [None])[0]
            
            if code:
                log(s_id, "SUCCESS", "Code Found: " + code, "INFO", {}, "", "", {}, "")
                # ... آپ یہاں لاگ ان والی API کال کر سکتے ہیں ...

        return {"status": "success"}

    except Exception as e:
        log(s_id, "ERROR", "", "", {}, "", "Error", {}, str(e))
        return {"status": "error", "message": str(e)}

@app.get("/api/get-logs")
def get_logs(id: str): return {"logs": logs_db.get(id, "")}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
