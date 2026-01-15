import os
import uvicorn
import requests
import json
from urllib.parse import urlparse, parse_qs
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI()

# --- ڈیٹا بیس ---
logs_db = {}

# --- 1. HAR File والے اصلی ہیڈرز (تاکہ SMS بلاک نہ ہو) ---
REAL_HEADERS = {
    "Host": "jazzdrive.com.pk",
    "Connection": "keep-alive",
    "sec-ch-ua": '"Chromium";v="139", "Not;A=Brand";v="99"',
    "sec-ch-ua-mobile": "?1", # HAR میں ?1 تھا (Android)، ہم اسے فالو کریں گے
    "sec-ch-ua-platform": '"Android"',
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br"
}

class PhoneRequest(BaseModel):
    phone: str
    session_id: str

class VerifyRequest(BaseModel):
    otp: str
    session_id: str
    verify_url: str

# --- HTML UI ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ur" dir="rtl">
<head>
    <title>Jazz Drive API Pro</title>
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
        <h2>🚀 Jazz Drive API (Anti-Block)</h2>
        <div id="step1" class="input-box">
            <p style="color:white">1. نمبر درج کریں:</p>
            <input type="text" id="phone" value="03027665767">
            <button onclick="startProcess()">Send OTP</button>
        </div>
        <div id="step2" class="input-box hidden">
            <p style="color:white">2. OTP درج کریں:</p>
            <input type="text" id="otp" placeholder="1234">
            <button onclick="verifyProcess()">Verify</button>
        </div>
        <div style="margin-bottom: 5px; text-align: right;">
            <button onclick="copyLogs()" style="background: #1f6feb;">Copy Logs</button>
        </div>
        <div id="terminal">Waiting...</div>
    </div>
    <script>
        let sessionKey = "sess_" + Date.now();
        let pollInterval = null;
        let verifyUrl = "";

        async function startProcess() {
            const phone = document.getElementById('phone').value;
            document.getElementById('step1').querySelector('button').disabled = true;
            document.getElementById('terminal').innerHTML = "Initializing...";
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
    entry = f"""
<div class="divider"></div>
<div class="info">🔹 <b>STEP: {title}</b></div>
<div class="req-head">➡️ REQUEST: {method} {req_url}</div>
<div class="info">Headers: {json.dumps(dict(req_headers), indent=2)}</div>
<div class="info">Body: {req_body}</div>
<div class="res-head">⬅️ RESPONSE: {res_status}</div>
<div class="info">Headers: {json.dumps(dict(res_headers), indent=2)}</div>
<div class="info">Body: {res_body[:500]}...</div>
"""
    logs_db[session_id] += entry

# --- API ENDPOINTS ---

@app.post("/api/send-otp")
def send_otp_api(data: PhoneRequest):
    s_id = data.session_id
    try:
        # **اہم ترین تبدیلی: سیشن کو پہلے گرم کریں**
        session = requests.Session()
        
        # Step 0: Visit Homepage (To get Cookies & look legitimate)
        log(s_id, "0. Warming up Session (Home Page)", "https://jazzdrive.com.pk/", "GET", REAL_HEADERS, "None", "Pending...", {}, "")
        r0 = session.get("https://jazzdrive.com.pk/", headers=REAL_HEADERS)
        log(s_id, "0. Warmup Result", "https://jazzdrive.com.pk/", "GET", r0.request.headers, "None", r0.status_code, r0.headers, "Cookies set!")

        # Step 1: Authorization
        url1 = "https://jazzdrive.com.pk/oauth2/authorization.php?response_type=code&client_id=web&state=66551&redirect_uri=https://cloud.jazzdrive.com.pk/ui/html/oauth.html"
        r1 = session.get(url1, headers=REAL_HEADERS, allow_redirects=False)
        log(s_id, "1. Get Signup ID", url1, "GET", r1.request.headers, "None", r1.status_code, r1.headers, "")
        
        if 'Location' not in r1.headers: return {"status": "fail", "message": "Signup ID Failed"}
        signup_url = f"https://jazzdrive.com.pk/oauth2/{r1.headers['Location']}"
        
        # Step 2: Send Phone (Using same Session + Headers)
        payload = {"enrichment_status": "", "msisdn": data.phone}
        # اہم: Referer ہیڈر شامل کرنا ضروری ہے
        post_headers = REAL_HEADERS.copy()
        post_headers["Content-Type"] = "application/x-www-form-urlencoded"
        post_headers["Origin"] = "https://jazzdrive.com.pk"
        post_headers["Referer"] = signup_url
        
        r2 = session.post(signup_url, data=payload, headers=post_headers, allow_redirects=False)
        log(s_id, "2. Send OTP", signup_url, "POST", r2.request.headers, str(payload), r2.status_code, r2.headers, "")
        
        if 'Location' not in r2.headers: return {"status": "fail", "message": "OTP Send Failed"}
        
        return {"status": "success", "verify_url": r2.headers['Location']}

    except Exception as e:
        log(s_id, "ERROR", "", "", {}, "", "Error", {}, str(e))
        return {"status": "error", "message": str(e)}

@app.post("/api/verify-otp")
def verify_otp_api(data: VerifyRequest):
    s_id = data.session_id
    try:
        # نوٹ: مثالی طور پر سیشن پچھلے سٹیپ سے آنا چاہیے، لیکن فی الحال نیا بنا رہے ہیں
        # اصل ایپ میں آپ سیشن کو محفوظ کر سکتے ہیں، لیکن کوکیز دوبارہ سیٹ کرنی پڑیں گی
        session = requests.Session() 
        # (یہاں سیشن ری سیٹ ہو گیا ہے، جو ایک مسئلہ ہو سکتا ہے، لیکن پہلے ٹیسٹ کرتے ہیں)
        
        # ری-وارم اپ (Re-Warmup) اگر سیشن الگ ہے
        session.get("https://jazzdrive.com.pk/", headers=REAL_HEADERS)

        # Step 3: Verify
        headers = REAL_HEADERS.copy()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Referer"] = data.verify_url
        headers["Origin"] = "https://jazzdrive.com.pk"
        
        r3 = session.post(data.verify_url, data={"otp": data.otp}, headers=headers, allow_redirects=False)
        log(s_id, "3. Verify OTP", data.verify_url, "POST", r3.request.headers, data.otp, r3.status_code, r3.headers, r3.text)
        
        if r3.status_code != 302: return {"status": "fail", "message": "Invalid OTP"}

        # Step 4: Follow Redirects
        auth_url = "https://jazzdrive.com.pk" + r3.headers['Location']
        r4 = session.get(auth_url, headers=REAL_HEADERS, allow_redirects=False)
        log(s_id, "4. Get Token Code", auth_url, "GET", r4.request.headers, "", r4.status_code, r4.headers, "")
        
        if 'Location' not in r4.headers: return {"status": "fail"}
        cloud_url = r4.headers['Location']
        
        # Step 5: Get Keys
        parsed = parse_qs(urlparse(cloud_url).query)
        code = parsed.get('code', [None])[0]
        
        if code:
            login_api = f"https://cloud.jazzdrive.com.pk/sapi/login/oauth?action=login&platform=web&keytype=authorizationcode&key={code}"
            # Cloud Headers (Important!)
            c_headers = REAL_HEADERS.copy()
            c_headers["Host"] = "cloud.jazzdrive.com.pk"
            c_headers["Referer"] = "https://cloud.jazzdrive.com.pk/"
            c_headers["X-deviceid"] = "web-ff039175658859f46aa02723b12ad9df"
            
            r5 = session.get(login_api, headers=c_headers)
            log(s_id, "5. Login Success", login_api, "GET", r5.request.headers, "", r5.status_code, r5.headers, r5.text)
            
        return {"status": "success"}

    except Exception as e:
        log(s_id, "ERROR", "", "", {}, "", "Error", {}, str(e))
        return {"status": "error", "message": str(e)}

@app.get("/api/get-logs")
def get_logs(id: str): return {"logs": logs_db.get(id, "")}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
