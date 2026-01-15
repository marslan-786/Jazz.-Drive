import os
import uvicorn
import requests
import json
import re
from urllib.parse import urlparse, parse_qs
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI()

# --- Professional PC Headers (To avoid detection) ---
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

# --- Data Models ---
class PhoneRequest(BaseModel):
    phone: str

class VerifyRequest(BaseModel):
    otp: str
    verify_url: str  # پچھلے سٹیپ سے ملا ہوا لنک

# --- HTML UI ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ur" dir="rtl">
<head>
    <title>Jazz Drive API Panel</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { background-color: #121212; color: #e0e0e0; font-family: sans-serif; padding: 20px; text-align: right; }
        .container { max-width: 600px; margin: 0 auto; background: #1e1e1e; padding: 20px; border-radius: 8px; border: 1px solid #333; }
        h2 { color: #bb86fc; border-bottom: 1px solid #333; padding-bottom: 10px; }
        input { width: 95%; padding: 12px; margin: 10px 0; background: #2c2c2c; border: 1px solid #444; color: white; border-radius: 4px; direction: ltr; }
        button { width: 100%; padding: 12px; background: #03dac6; color: black; font-weight: bold; border: none; border-radius: 4px; cursor: pointer; }
        button:disabled { background: #555; }
        .hidden { display: none; }
        pre { background: #000; padding: 10px; border: 1px solid #333; direction: ltr; text-align: left; overflow-x: scroll; color: #0f0; }
        .label { color: #888; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <h2>⚡ Jazz Drive API Tool</h2>
        
        <div id="step1">
            <p>اپنا جیز نمبر درج کریں:</p>
            <input type="text" id="phone" placeholder="030xxxxxxxxx" value="03027665767">
            <button onclick="sendOtp()" id="btn1">Send OTP</button>
        </div>

        <div id="step2" class="hidden">
            <p>موصول ہونے والا OTP درج کریں:</p>
            <input type="text" id="otp" placeholder="1234">
            <button onclick="verifyLogin()" id="btn2">Verify & Get Token</button>
        </div>

        <div id="result" class="hidden">
            <p>✅ <b>Final API Response:</b></p>
            <pre id="jsonOutput">Waiting...</pre>
        </div>
    </div>

    <script>
        let verifyUrl = "";

        async function sendOtp() {
            const phone = document.getElementById('phone').value;
            document.getElementById('btn1').innerText = "Sending...";
            document.getElementById('btn1').disabled = true;

            try {
                const res = await fetch('/api/send-otp', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({phone: phone})
                });
                const data = await res.json();

                if(data.status === 'success') {
                    verifyUrl = data.verify_url; // Save for next step
                    document.getElementById('step1').classList.add('hidden');
                    document.getElementById('step2').classList.remove('hidden');
                } else {
                    alert("Error: " + data.message);
                    document.getElementById('btn1').disabled = false;
                    document.getElementById('btn1').innerText = "Send OTP";
                }
            } catch(e) { alert("Network Error"); }
        }

        async function verifyLogin() {
            const otp = document.getElementById('otp').value;
            document.getElementById('btn2').innerText = "Verifying & Fetching Tokens...";
            document.getElementById('btn2').disabled = true;

            try {
                const res = await fetch('/api/verify', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({otp: otp, verify_url: verifyUrl})
                });
                const data = await res.json();

                document.getElementById('step2').classList.add('hidden');
                document.getElementById('result').classList.remove('hidden');
                
                // Show JSON nicely
                document.getElementById('jsonOutput').innerText = JSON.stringify(data, null, 2);

            } catch(e) { 
                document.getElementById('jsonOutput').innerText = "Error: " + e;
            }
        }
    </script>
</body>
</html>
"""

@app.get("/")
def home():
    return HTMLResponse(HTML_TEMPLATE)

# --- Step 1: Send OTP ---
@app.post("/api/send-otp")
def api_send_otp(req: PhoneRequest):
    try:
        session = requests.Session()
        
        # 1. Authorize URL (Get Signup ID)
        # HAR File Step 1
        auth_url = "https://jazzdrive.com.pk/oauth2/authorization.php?response_type=code&client_id=web&state=66551&redirect_uri=https://cloud.jazzdrive.com.pk/ui/html/oauth.html"
        
        r1 = session.get(auth_url, headers=PC_HEADERS, allow_redirects=False)
        if 'Location' not in r1.headers:
            return {"status": "fail", "message": "Failed to get Signup ID"}
        
        signup_relative_url = r1.headers['Location'] # signup.php?id=...
        signup_full_url = f"https://jazzdrive.com.pk/oauth2/{signup_relative_url}"
        
        # 2. Send Phone Number (Get Verify URL)
        # HAR File Step 2
        payload = {"enrichment_status": "", "msisdn": req.phone}
        pc_headers_post = PC_HEADERS.copy()
        pc_headers_post["Content-Type"] = "application/x-www-form-urlencoded"
        pc_headers_post["Origin"] = "https://jazzdrive.com.pk"
        pc_headers_post["Referer"] = signup_full_url

        r2 = session.post(signup_full_url, data=payload, headers=pc_headers_post, allow_redirects=False)
        
        if 'Location' not in r2.headers:
            return {"status": "fail", "message": "Failed to send OTP (No redirect)"}
        
        verify_url = r2.headers['Location'] # https://jazzdrive.com.pk/verify.php?id=...
        
        return {
            "status": "success", 
            "verify_url": verify_url # یہ اگلی ریکویسٹ کے لیے چاہیے
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


# --- Step 2: Verify & Get Final Token ---
@app.post("/api/verify")
def api_verify_login(req: VerifyRequest):
    try:
        session = requests.Session()
        
        # 1. Verify OTP
        # HAR File Step 3
        pc_headers_post = PC_HEADERS.copy()
        pc_headers_post["Content-Type"] = "application/x-www-form-urlencoded"
        pc_headers_post["Origin"] = "https://jazzdrive.com.pk"
        pc_headers_post["Referer"] = req.verify_url
        
        r1 = session.post(req.verify_url, data={"otp": req.otp}, headers=pc_headers_post, allow_redirects=False)
        
        if 'Location' not in r1.headers:
            return {"status": "fail", "message": "Invalid OTP (No redirect)"}
        
        # /authorize.php?response_type=...
        authorize_relative = r1.headers['Location']
        authorize_url = f"https://jazzdrive.com.pk{authorize_relative}"
        
        # 2. Get Authorization Code
        # HAR File Step 4
        r2 = session.get(authorize_url, headers=PC_HEADERS, allow_redirects=False)
        
        if 'Location' not in r2.headers:
            return {"status": "fail", "message": "Authorization Failed"}
        
        # https://cloud.jazzdrive.com.pk/ui/html/oauth.html?code=XYZ...
        cloud_redirect_url = r2.headers['Location']
        
        # Extract Code from URL
        parsed = urlparse(cloud_redirect_url)
        params = parse_qs(parsed.query)
        oauth_code = params.get('code', [None])[0]
        
        if not oauth_code:
            return {"status": "fail", "message": "OAuth Code not found in URL"}

        # 3. Exchange Code for Access Token & Validation Key
        # HAR File Step 6 (This is the Login API)
        login_api = f"https://cloud.jazzdrive.com.pk/sapi/login/oauth?action=login&platform=web&keytype=authorizationcode&key={oauth_code}"
        
        # Headers for Cloud Domain
        cloud_headers = PC_HEADERS.copy()
        cloud_headers["Referer"] = "https://cloud.jazzdrive.com.pk/"
        cloud_headers["Origin"] = "https://cloud.jazzdrive.com.pk"
        cloud_headers["X-deviceid"] = "web-ff039175658859f46aa02723b12ad9df" # From HAR
        
        r3 = session.get(login_api, headers=cloud_headers)
        login_data = r3.json()
        
        # Extract Keys
        access_token = login_data.get("data", {}).get("access_token")
        validation_key = login_data.get("data", {}).get("validationkey")
        
        if not validation_key:
            return {"status": "fail", "message": "Login successful but keys missing", "debug": login_data}

        # 4. Final API Call (Testing Access)
        # HAR File Last Step (/sapi/label)
        final_api = f"https://cloud.jazzdrive.com.pk/sapi/label?action=get&limit=100&shared_items=true&validationkey={validation_key}"
        
        payload = {"data":{"types":["file"],"origin":["omh","shared_label"]}}
        
        r4 = session.post(final_api, json=payload, headers=cloud_headers)
        
        # 5. Return Everything to User
        return {
            "status": "success",
            "message": "Login Completed!",
            "credentials": {
                "validation_key": validation_key,
                "access_token": access_token[:20] + "...", # چھپا دیا تاکہ سکرین نہ بھرے
                "jsessionid": session.cookies.get("JSESSIONID")
            },
            "final_api_response": r4.json()
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
