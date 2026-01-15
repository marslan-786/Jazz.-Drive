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

# --- Global Logs ---
logs_db = {}

# --- HAR File Headers (Desktop Mode) ---
# یہ وہ ہیڈرز ہیں جو آپ کی HAR فائل میں پی سی کے لیے استعمال ہوئے
COMMON_HEADERS = {
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

# کلاؤڈ API کے لیے خاص ہیڈرز
CLOUD_API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "X-deviceid": "web-ff039175658859f46aa02723b12ad9df", # HAR سے لیا گیا
    "Origin": "https://cloud.jazzdrive.com.pk",
    "Referer": "https://cloud.jazzdrive.com.pk/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin"
}

# --- Data Models ---
class PhoneRequest(BaseModel):
    phone: str
    session_id: str

class VerifyRequest(BaseModel):
    otp: str
    session_id: str
    verify_url: str
    cookies: dict  # ہم کوکیز فرنٹ اینڈ سے واپس لیں گے تاکہ سیشن ضائع نہ ہو

# --- HTML UI ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Jazz Drive Final API</title>
    <style>
        body { background-color: #0d1117; color: #c9d1d9; font-family: monospace; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; }
        .panel { background: #161b22; border: 1px solid #30363d; padding: 20px; margin-bottom: 20px; border-radius: 6px; }
        input { background: #0d1117; border: 1px solid #30363d; color: #fff; padding: 10px; width: 60%; }
        button { background: #238636; color: white; border: none; padding: 10px 20px; cursor: pointer; font-weight: bold; }
        #terminal { background: #000; border: 2px solid #3fb950; height: 500px; overflow-y: scroll; padding: 15px; color: #0f0; white-space: pre-wrap; }
        .req { color: #58a6ff; } .res { color: #d29922; }
        .hidden { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🚀 Jazz Drive: Cloud to Label API</h2>
        
        <div id="step1" class="panel">
            <p>1. Enter Number (Browser Load -> API Send):</p>
            <input type="text" id="phone" value="03027665767">
            <button onclick="startFlow()">Start</button>
        </div>

        <div id="step2" class="panel hidden">
            <p>2. Enter OTP (Full API Chain):</p>
            <input type="text" id="otp" placeholder="1234">
            <button onclick="verifyFlow()">Verify & Fetch Data</button>
        </div>

        <div id="terminal">Waiting...</div>
    </div>

    <script>
        let sessionKey = "sess_" + Date.now();
        let verifyUrl = "";
        let savedCookies = {};
        let pollInterval = null;

        async function startFlow() {
            const phone = document.getElementById('phone').value;
            document.getElementById('step1').querySelector('button').disabled = true;
            document.getElementById('terminal').innerHTML = "Initializing Browser for Cookie Warmup...\n";
            startPolling();

            try {
                const res = await fetch('/api/start-flow', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({phone: phone, session_id: sessionKey})
                });
                const data = await res.json();
                if(data.status === 'success') {
                    verifyUrl = data.verify_url;
                    savedCookies = data.cookies;
                    document.getElementById('step1').classList.add('hidden');
                    document.getElementById('step2').classList.remove('hidden');
                } else {
                    alert("Error: " + data.message);
                    document.getElementById('step1').querySelector('button').disabled = false;
                }
            } catch(e) { alert(e); }
        }

        async function verifyFlow() {
            const otp = document.getElementById('otp').value;
            document.getElementById('step2').querySelector('button').disabled = true;
            
            try {
                const res = await fetch('/api/verify-chain', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        otp: otp, session_id: sessionKey, 
                        verify_url: verifyUrl, cookies: savedCookies
                    })
                });
                const data = await res.json();
                // Final Result is logged in terminal via polling
            } catch(e) { alert(e); }
        }

        function startPolling() {
            pollInterval = setInterval(async () => {
                const res = await fetch('/api/get-logs?id=' + sessionKey);
                const data = await res.json();
                if(data.logs) {
                    const t = document.getElementById('terminal');
                    t.innerHTML = data.logs;
                    t.scrollTop = t.scrollHeight;
                }
            }, 1000);
        }
    </script>
</body>
</html>
"""

@app.get("/")
def home(): return HTMLResponse(HTML_TEMPLATE)

def log(sid, title, method, url, status, detail):
    if sid not in logs_db: logs_db[sid] = ""
    logs_db[sid] += f"\n🔹 <b>{title}</b>\n<span class='req'>➡️ {method} {url}</span>\n<span class='res'>⬅️ Status: {status}</span>\n{detail}\n----------------------------------\n"

# --- 1. START FLOW (Browser -> API) ---
@app.post("/api/start-flow")
def start_flow_api(data: PhoneRequest):
    sid = data.session_id
    try:
        signup_url = None
        browser_cookies = {}

        # A. Browser Step: Load Cloud Page to get valid Redirect & Cookies
        log(sid, "1. Browser Warmup", "BROWSER", "https://cloud.jazzdrive.com.pk", "Loading...", "Waiting for redirect to signup.php...")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(user_agent=COMMON_HEADERS["User-Agent"])
            page = context.new_page()
            
            page.goto("https://cloud.jazzdrive.com.pk", timeout=60000)
            
            try:
                # Wait for redirect to signup.php
                page.wait_for_url("**signup.php**", timeout=45000)
                signup_url = page.url
                
                # Extract Cookies
                for c in context.cookies():
                    browser_cookies[c['name']] = c['value']
                
                log(sid, "1. Browser Success", "INFO", signup_url, "OK", f"Extracted {len(browser_cookies)} Cookies")
            except Exception as e:
                browser.close()
                log(sid, "Browser Error", "FAIL", "", "Timeout", str(e))
                return {"status": "fail", "message": "Browser failed to reach signup"}
            
            browser.close()

        # B. API Step: Send OTP (using Browser Cookies)
        if not signup_url: return {"status": "fail"}
        
        session = requests.Session()
        session.cookies.update(browser_cookies)
        
        payload = {"enrichment_status": "", "msisdn": data.phone}
        headers = COMMON_HEADERS.copy()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Referer"] = signup_url # Very Important!
        headers["Origin"] = "https://jazzdrive.com.pk"
        
        log(sid, "2. Sending SMS (API)", "POST", signup_url, "Sending...", f"Payload: {payload}")
        r = session.post(signup_url, data=payload, headers=headers, allow_redirects=False)
        
        log(sid, "2. SMS Response", "INFO", "Status", str(r.status_code), f"Location: {r.headers.get('Location')}")
        
        if r.status_code == 302 and 'Location' in r.headers:
            return {
                "status": "success", 
                "verify_url": r.headers['Location'],
                "cookies": session.cookies.get_dict() # Return updated cookies
            }
        else:
            return {"status": "fail", "message": "SMS Sending Failed"}

    except Exception as e:
        log(sid, "System Error", "ERROR", str(e), "500", "")
        return {"status": "error", "message": str(e)}


# --- 2. VERIFY CHAIN (API Only) ---
@app.post("/api/verify-chain")
def verify_chain_api(data: VerifyRequest):
    sid = data.session_id
    try:
        session = requests.Session()
        session.cookies.update(data.cookies)
        
        # A. Verify OTP
        headers = COMMON_HEADERS.copy()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Referer"] = data.verify_url
        headers["Origin"] = "https://jazzdrive.com.pk"
        
        log(sid, "3. Verifying OTP", "POST", data.verify_url, "Sending...", f"Code: {data.otp}")
        r1 = session.post(data.verify_url, data={"otp": data.otp}, headers=headers, allow_redirects=False)
        log(sid, "3. Verify Result", "INFO", str(r1.status_code), r1.reason, f"Location: {r1.headers.get('Location')}")
        
        if r1.status_code != 302: return {"status": "fail", "message": "Invalid OTP"}
        
        # B. Authorize Redirect
        auth_url = r1.headers['Location']
        if auth_url.startswith("/"): auth_url = "https://jazzdrive.com.pk" + auth_url
        
        log(sid, "4. Authorization", "GET", auth_url, "Sending...", "")
        r2 = session.get(auth_url, headers=COMMON_HEADERS, allow_redirects=False)
        
        cloud_redirect = r2.headers.get('Location')
        if not cloud_redirect: return {"status": "fail", "message": "Auth Failed"}
        
        # C. Get OAuth Code (from Cloud URL)
        log(sid, "5. Cloud Redirect", "GET", cloud_redirect, "Found", "")
        parsed = parse_qs(urlparse(cloud_redirect).query)
        oauth_code = parsed.get('code', [None])[0]
        
        if not oauth_code: return {"status": "fail", "message": "No Code Found"}
        
        # D. Login / Exchange Token (sapi/login/oauth)
        login_api = f"https://cloud.jazzdrive.com.pk/sapi/login/oauth?action=login&platform=web&keytype=authorizationcode&key={oauth_code}"
        log(sid, "6. Exchanging Token", "GET", login_api, "Sending...", "")
        
        r3 = session.get(login_api, headers=CLOUD_API_HEADERS)
        login_data = r3.json()
        
        val_key = login_data.get("data", {}).get("validationkey")
        if not val_key:
            log(sid, "Login Failed", "ERROR", "", "", str(login_data))
            return {"status": "fail"}
            
        log(sid, "Login Success", "INFO", "ValidationKey Found", "OK", val_key)

        # E. FINAL STEP: Get Labels (sapi/label)
        final_url = f"https://cloud.jazzdrive.com.pk/sapi/label?action=get&limit=100&shared_items=true&validationkey={val_key}"
        payload = {"data":{"types":["file"],"origin":["omh","shared_label"]}}
        
        # Update headers specifically for this POST request
        final_headers = CLOUD_API_HEADERS.copy()
        final_headers["Content-Type"] = "application/json;charset=UTF-8"
        
        log(sid, "7. Fetching Labels (Final)", "POST", final_url, "Sending...", json.dumps(payload))
        
        r4 = session.post(final_url, json=payload, headers=final_headers)
        
        # PRINT FINAL RESPONSE
        log(sid, "🎉 FINAL RESPONSE", "SUCCESS", "200 OK", "JSON Data:", json.dumps(r4.json(), indent=2))
        
        return {"status": "success", "data": r4.json()}

    except Exception as e:
        log(sid, "CRITICAL ERROR", str(e), "FAIL", "", "")
        return {"status": "error", "message": str(e)}

@app.get("/api/get-logs")
def logs_api(id: str): return {"logs": logs_db.get(id, "")}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
