import os
import uvicorn
import requests
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from playwright.sync_api import sync_playwright

app = FastAPI()

# --- ڈیٹا ماڈلز ---
class NumberRequest(BaseModel):
    phone: str

class OtpRequest(BaseModel):
    otp: str
    session_id: str

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://jazzdrive.com.pk",
    "Referer": "https://jazzdrive.com.pk"
}

# --- 1. فرنٹ اینڈ (HTML UI) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Jazz Drive Command Center</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: 'Courier New', monospace; background: #0d1117; color: #58a6ff; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; border: 1px solid #30363d; padding: 20px; border-radius: 6px; background: #161b22; }
        h2 { border-bottom: 1px solid #30363d; padding-bottom: 10px; color: #c9d1d9; }
        
        /* ان پٹ سٹائل */
        .input-group { margin: 15px 0; display: flex; gap: 10px; }
        input { 
            background: #0d1117; border: 1px solid #30363d; color: #c9d1d9; 
            padding: 10px; flex-grow: 1; font-family: inherit; border-radius: 4px;
        }
        button { 
            padding: 10px 20px; cursor: pointer; background: #238636; color: white; 
            border: none; font-weight: bold; border-radius: 4px; font-family: inherit;
        }
        button:disabled { background: #30363d; cursor: not-allowed; }
        button.secondary { background: #1f6feb; }

        /* ٹرمینل لاگز */
        #terminal { 
            background: #000; border: 1px solid #30363d; padding: 15px; 
            height: 350px; overflow-y: scroll; white-space: pre-wrap; 
            margin-top: 20px; font-size: 13px; color: #adbac7; border-radius: 4px;
        }
        
        .log-info { color: #58a6ff; }
        .log-success { color: #3fb950; }
        .log-error { color: #f85149; }
        .log-warn { color: #d29922; }
        
        .hidden { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h2>⚡ Jazz Drive Auth Terminal</h2>
        
        <div id="step1">
            <p style="color: #c9d1d9;">Step 1: Enter User Phone Number</p>
            <div class="input-group">
                <input type="text" id="phone" placeholder="030xxxxxxxxx" value="03027665767">
                <button onclick="startProcess()" id="btnStep1">Send OTP</button>
            </div>
        </div>

        <div id="step2" class="hidden">
            <p style="color: #c9d1d9;">Step 2: Enter OTP Received on Mobile</p>
            <div class="input-group">
                <input type="text" id="otp" placeholder="e.g. 1234">
                <button onclick="verifyCode()" id="btnStep2">Verify Login</button>
            </div>
        </div>

        <div id="terminal">System Ready... Waiting for input.</div>
        <div style="margin-top: 10px; text-align: right;">
             <button class="secondary" onclick="copyLogs()">Copy Logs</button>
        </div>
    </div>

    <script>
        let currentSessionId = "";

        function log(message, type="info") {
            const term = document.getElementById('terminal');
            const timestamp = new Date().toLocaleTimeString();
            let colorClass = "log-info";
            if(type === "success") colorClass = "log-success";
            if(type === "error") colorClass = "log-error";
            
            term.innerHTML += `<div class="${colorClass}">[${timestamp}] ${message}</div>`;
            term.scrollTop = term.scrollHeight;
        }

        async function startProcess() {
            const phone = document.getElementById('phone').value;
            if(!phone) { alert("Please enter a number"); return; }

            document.getElementById('btnStep1').disabled = true;
            log("🚀 Starting Process for " + phone + "...");
            log("⏳ Launching background browser to extract Session ID...");

            try {
                const response = await fetch('/api/send-otp', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ phone: phone })
                });
                
                const data = await response.json();

                if (data.status === "success") {
                    currentSessionId = data.session_id;
                    log("✅ Signup ID Extracted: " + currentSessionId.substring(0, 20) + "...", "success");
                    log("📤 Sending OTP Request via API...", "info");
                    log("✅ OTP Sent Successfully! Please check SMS.", "success");
                    
                    // Switch to Step 2
                    document.getElementById('step1').classList.add('hidden');
                    document.getElementById('step2').classList.remove('hidden');
                } else {
                    log("❌ Error: " + data.message, "error");
                    if(data.debug) log("Debug: " + data.debug, "error");
                    document.getElementById('btnStep1').disabled = false;
                }
            } catch (err) {
                log("❌ Network/Server Error: " + err, "error");
                document.getElementById('btnStep1').disabled = false;
            }
        }

        async function verifyCode() {
            const otp = document.getElementById('otp').value;
            if(!otp) { alert("Enter OTP"); return; }

            document.getElementById('btnStep2').disabled = true;
            log("⏳ Verifying OTP: " + otp + "...");

            try {
                const response = await fetch('/api/verify-otp', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ otp: otp, session_id: currentSessionId })
                });
                
                const data = await response.json();

                if (data.status === "success") {
                    log("🎉 LOGIN SUCCESSFUL!", "success");
                    log("🔑 AUTH DATA (Save this):", "success");
                    log(JSON.stringify(data.auth_data, null, 2), "success");
                    log("-----------------------------------");
                    log("You can now use these cookies to download files.");
                } else {
                    log("❌ Verification Failed: " + data.message, "error");
                    document.getElementById('btnStep2').disabled = false;
                }
            } catch (err) {
                log("❌ Error: " + err, "error");
                document.getElementById('btnStep2').disabled = false;
            }
        }

        function copyLogs() {
            const text = document.getElementById('terminal').innerText;
            navigator.clipboard.writeText(text);
            alert("Logs copied!");
        }
    </script>
</body>
</html>
"""

# --- 2. روٹس (Backend Routes) ---

@app.get("/")
def home():
    return HTMLResponse(content=HTML_TEMPLATE)

@app.post("/api/send-otp")
def api_send_otp(req: NumberRequest):
    print(f"Request received for: {req.phone}")
    
    # 1. Playwright Logic to get ID
    session_id = None
    try:
        with sync_playwright() as p:
            # نیا ورژن استعمال کرنے کے لیے Dockerfile اپڈیٹ ہونا ضروری ہے
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(user_agent=HEADERS["User-Agent"])
            page = context.new_page()
            page.set_default_timeout(60000)

            try:
                page.goto("https://cloud.jazzdrive.com.pk")
                # Wait for ID
                page.wait_for_url("**id=*", timeout=45000)
                final_url = page.url
                
                if "id=" in final_url:
                    session_id = final_url.split("id=")[1].split("&")[0]
            except Exception as e:
                print(f"Browser Step Error: {e}")
            finally:
                browser.close()

        if not session_id:
            return {"status": "fail", "message": "Could not extract Session ID (Timeout or Blocked)"}

        # 2. Send OTP via API using extracted ID
        # نوٹ: ہم 'signup.php' استعمال کر رہے ہیں جیسا کہ لاگز میں دیکھا گیا
        api_url = f"https://jazzdrive.com.pk/oauth2/signup.php?id={session_id}"
        payload = {"msisdn": req.phone, "enrichment_status": ""}
        
        resp = requests.post(api_url, data=payload, headers=HEADERS)
        
        if resp.status_code in [200, 302]:
             return {"status": "success", "session_id": session_id}
        else:
             return {"status": "fail", "message": "Jazz API rejected the number", "debug": resp.text}

    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/verify-otp")
def api_verify_otp(req: OtpRequest):
    # لاگ ان کے لیے دونوں URLs ٹرائی کریں گے (verify.php اور signup.php)
    
    # Method A: verify.php
    url_a = f"https://jazzdrive.com.pk/verify.php?id={req.session_id}"
    session = requests.Session()
    
    try:
        resp = session.post(url_a, data={"otp": req.otp}, headers=HEADERS, allow_redirects=False)
        
        if resp.status_code == 302:
            return {"status": "success", "auth_data": session.cookies.get_dict()}
        
        # Method B: signup.php (Fallback)
        url_b = f"https://jazzdrive.com.pk/oauth2/signup.php?id={req.session_id}"
        resp2 = session.post(url_b, data={"otp": req.otp}, headers=HEADERS, allow_redirects=False)
        
        if resp2.status_code == 302:
             return {"status": "success", "auth_data": session.cookies.get_dict()}
        
        return {"status": "fail", "message": "Invalid OTP code"}

    except Exception as e:
         return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
