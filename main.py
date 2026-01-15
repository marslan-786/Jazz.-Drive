import os
import uvicorn
import requests
import json
import time
from urllib.parse import urlparse, parse_qs
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI()

# --- ڈیٹا بیس (لاگز محفوظ کرنے کے لیے) ---
logs_db = {}

# --- Professional Headers (Anti-Detect) ---
PC_HEADERS = {
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

# --- 1. HTML UI (Terminal View) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ur" dir="rtl">
<head>
    <title>Jazz API Debugger</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { background-color: #0d1117; color: #c9d1d9; font-family: monospace; padding: 20px; direction: ltr; }
        .container { max-width: 900px; margin: 0 auto; }
        
        .input-box { background: #161b22; padding: 20px; border: 1px solid #30363d; border-radius: 6px; margin-bottom: 20px; }
        input { background: #0d1117; border: 1px solid #30363d; color: #fff; padding: 10px; width: 60%; }
        button { background: #238636; color: white; border: none; padding: 10px 20px; cursor: pointer; font-weight: bold; }
        
        /* ٹرمینل سٹائل */
        #terminal { 
            background: #000; border: 2px solid #3fb950; height: 500px; 
            overflow-y: scroll; padding: 15px; font-size: 12px; color: #0f0; 
            white-space: pre-wrap; font-family: 'Courier New', monospace;
        }
        
        .req-head { color: #58a6ff; font-weight: bold; } /* Request Blue */
        .res-head { color: #d29922; font-weight: bold; } /* Response Orange */
        .success { color: #3fb950; } 
        .error { color: #ff7b72; }
        .info { color: #8b949e; }
        .divider { border-bottom: 1px dashed #30363d; margin: 10px 0; }
        
        .hidden { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🛠️ Jazz Drive API Inspector</h2>
        
        <div id="step1" class="input-box">
            <p style="color:white">1. نمبر درج کریں:</p>
            <input type="text" id="phone" value="03027665767">
            <button onclick="startProcess()">Start API Trace</button>
        </div>

        <div id="step2" class="input-box hidden">
            <p style="color:white">2. OTP درج کریں:</p>
            <input type="text" id="otp" placeholder="1234">
            <button onclick="verifyProcess()">Verify & Log</button>
        </div>

        <div style="margin-bottom: 5px; text-align: right;">
            <button onclick="copyLogs()" style="background: #1f6feb;">Copy Full Logs</button>
            <button onclick="clearLogs()" style="background: #da3633;">Clear</button>
        </div>
        
        <div id="terminal">System Ready... Waiting for input.</div>
    </div>

    <script>
        let sessionKey = "sess_" + Date.now();
        let pollInterval = null;
        let verifyUrl = "";

        function logToTerm(html) {
            const t = document.getElementById('terminal');
            t.innerHTML += html;
            t.scrollTop = t.scrollHeight;
        }

        async function startProcess() {
            const phone = document.getElementById('phone').value;
            document.getElementById('step1').querySelector('button').disabled = true;
            document.getElementById('terminal').innerHTML = "<div class='info'>🚀 Starting Sequence...</div>";
            
            // Start Polling for logs
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
            } catch(e) { alert("Network Error: " + e); }
        }

        async function verifyProcess() {
            const otp = document.getElementById('otp').value;
            document.getElementById('step2').querySelector('button').disabled = true;

            try {
                const res = await fetch('/api/verify-otp', {
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
                        document.getElementById('terminal').innerHTML = data.logs;
                        document.getElementById('terminal').scrollTop = document.getElementById('terminal').scrollHeight;
                    }
                } catch(e) {}
            }, 1000);
        }

        function copyLogs() {
            const text = document.getElementById('terminal').innerText;
            navigator.clipboard.writeText(text);
            alert("Logs Copied!");
        }
        function clearLogs() {
            document.getElementById('terminal').innerHTML = "Logs Cleared.";
        }
    </script>
</body>
</html>
"""

@app.get("/")
def home():
    return HTMLResponse(HTML_TEMPLATE)

# --- Logger Helper ---
def log(session_id, title, req_url, method, req_headers, req_body, res_status, res_headers, res_body):
    if session_id not in logs_db: logs_db[session_id] = ""
    
    # فارمیٹنگ (Formatting)
    entry = f"""
<div class="divider"></div>
<div class="info">🔹 <b>STEP: {title}</b></div>
<div class="req-head">➡️ REQUEST: {method} {req_url}</div>
<div class="info">Headers: {json.dumps(dict(req_headers), indent=2)}</div>
<div class="info">Body: {req_body}</div>

<div class="res-head">⬅️ RESPONSE: {res_status}</div>
<div class="info">Headers: {json.dumps(dict(res_headers), indent=2)}</div>
<div class="info">Body: {res_body[:1000]}... (truncated)</div>
"""
    logs_db[session_id] += entry

# --- API Endpoints ---

@app.post("/api/send-otp")
def send_otp_api(data: PhoneRequest):
    s_id = data.session_id
    try:
        session = requests.Session()
        
        # 1. Authorization Request
        url1 = "https://jazzdrive.com.pk/oauth2/authorization.php?response_type=code&client_id=web&state=66551&redirect_uri=https://cloud.jazzdrive.com.pk/ui/html/oauth.html"
        
        log(s_id, "1. Getting Signup ID", url1, "GET", PC_HEADERS, "None", "Pending...", {}, "")
        
        r1 = session.get(url1, headers=PC_HEADERS, allow_redirects=False)
        log(s_id, "1. Result", url1, "GET", r1.request.headers, "None", r1.status_code, r1.headers, r1.text)
        
        if 'Location' not in r1.headers:
            return {"status": "fail", "message": "No Signup ID Location found"}
            
        signup_url = f"https://jazzdrive.com.pk/oauth2/{r1.headers['Location']}"
        
        # 2. Signup Request (Send Phone)
        payload = {"enrichment_status": "", "msisdn": data.phone}
        post_headers = PC_HEADERS.copy()
        post_headers["Content-Type"] = "application/x-www-form-urlencoded"
        post_headers["Origin"] = "https://jazzdrive.com.pk"
        post_headers["Referer"] = signup_url
        
        log(s_id, "2. Sending Phone Number", signup_url, "POST", post_headers, str(payload), "Pending...", {}, "")
        
        r2 = session.post(signup_url, data=payload, headers=post_headers, allow_redirects=False)
        log(s_id, "2. Result", signup_url, "POST", r2.request.headers, r2.request.body, r2.status_code, r2.headers, r2.text)
        
        if 'Location' not in r2.headers:
            return {"status": "fail", "message": "OTP Send Failed (No Redirect)"}
            
        return {"status": "success", "verify_url": r2.headers['Location']}

    except Exception as e:
        log(s_id, "ERROR", "", "", {}, "", "ERROR", {}, str(e))
        return {"status": "error", "message": str(e)}

@app.post("/api/verify-otp")
def verify_otp_api(data: VerifyRequest):
    s_id = data.session_id
    try:
        session = requests.Session()
        
        # 3. Verify OTP Request
        verify_url = data.verify_url
        payload = {"otp": data.otp}
        
        headers = PC_HEADERS.copy()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Referer"] = verify_url
        
        log(s_id, "3. Verifying OTP", verify_url, "POST", headers, str(payload), "Pending...", {}, "")
        
        r3 = session.post(verify_url, data=payload, headers=headers, allow_redirects=False)
        log(s_id, "3. Result", verify_url, "POST", r3.request.headers, r3.request.body, r3.status_code, r3.headers, r3.text)
        
        if r3.status_code != 302:
             log(s_id, "FAILURE", "", "", {}, "", "Failed", {}, "Status not 302. OTP might be wrong.")
             return {"status": "fail", "message": "Invalid OTP"}

        # 4. Follow Redirect (Authorize)
        auth_url = "https://jazzdrive.com.pk" + r3.headers['Location']
        log(s_id, "4. Getting Token Code", auth_url, "GET", PC_HEADERS, "None", "Pending...", {}, "")
        
        r4 = session.get(auth_url, headers=PC_HEADERS, allow_redirects=False)
        log(s_id, "4. Result", auth_url, "GET", r4.request.headers, "None", r4.status_code, r4.headers, r4.text)
        
        if 'Location' not in r4.headers:
             return {"status": "fail", "message": "Authorization Failed"}
             
        # Extract Code
        cloud_url = r4.headers['Location']
        log(s_id, "5. Cloud Redirect found", cloud_url, "INFO", {}, "", "", {}, "")
        
        parsed = parse_qs(urlparse(cloud_url).query)
        code = parsed.get('code', [None])[0]
        
        if not code:
             log(s_id, "ERROR", "", "", {}, "", "No Code", {}, "Could not find 'code' in URL")
             return {"status": "fail"}

        # 6. Exchange Code for Keys (Login API)
        login_api = f"https://cloud.jazzdrive.com.pk/sapi/login/oauth?action=login&platform=web&keytype=authorizationcode&key={code}"
        cloud_headers = PC_HEADERS.copy()
        cloud_headers["Referer"] = "https://cloud.jazzdrive.com.pk/"
        
        log(s_id, "6. Final Login Call", login_api, "GET", cloud_headers, "None", "Pending...", {}, "")
        
        r5 = session.get(login_api, headers=cloud_headers)
        log(s_id, "6. Result (KEYS HERE)", login_api, "GET", r5.request.headers, "None", r5.status_code, r5.headers, r5.text)
        
        return {"status": "success"}

    except Exception as e:
        log(s_id, "ERROR", "", "", {}, "", "ERROR", {}, str(e))
        return {"status": "error", "message": str(e)}

@app.get("/api/get-logs")
def get_logs(id: str):
    return {"logs": logs_db.get(id, "")}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
