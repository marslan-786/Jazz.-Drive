import time
import json
import requests
import uuid
import os
import io
import random
from flask import Flask, Response, request, render_template_string, stream_with_context
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)

# ==========================================
# HTML TEMPLATE
# ==========================================
HTML_CODE = """
<!DOCTYPE html>
<html lang="ur" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jazz Drive Upload Fix</title>
    <style>
        body { background-color: #1e1e1e; color: #fff; font-family: 'Courier New', monospace; margin: 0; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { text-align: center; color: #00ff00; }
        .control-panel { background: #2d2d2d; padding: 20px; border-radius: 10px; margin-bottom: 20px; border: 1px solid #444; }
        input { width: 100%; padding: 10px; margin: 10px 0; background: #444; border: 1px solid #666; color: #fff; border-radius: 5px; font-size: 16px; }
        button { width: 100%; padding: 12px; background: #007bff; border: none; color: white; border-radius: 5px; cursor: pointer; font-size: 16px; font-weight: bold; margin-top: 5px;}
        button:hover { background: #0056b3; }
        button:disabled { background: #555; cursor: not-allowed; }
        
        #terminal { 
            background-color: #000; 
            border: 2px solid #00ff00; 
            padding: 15px; 
            height: 400px; 
            overflow-y: scroll; 
            white-space: pre-wrap; 
            font-size: 14px; 
            border-radius: 5px;
            box-shadow: 0 0 15px rgba(0, 255, 0, 0.2);
        }
        .log-line { margin: 2px 0; border-bottom: 1px solid #333; padding-bottom: 2px; }
        .log-info { color: #00ffff; }
        .log-success { color: #00ff00; }
        .log-error { color: #ff4444; }
        .log-header { color: #ffff00; font-size: 12px; }
        .hidden { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Jazz Drive Upload Fix</h1>
        
        <div class="control-panel">
            <label>موبائل نمبر (0300...):</label>
            <input type="text" id="phone_number" placeholder="030XXXXXXX">
            
            <button id="startBtn" onclick="startProcess()">اسٹارٹ (Start)</button>
            
            <div id="otpSection" class="hidden">
                <label>OTP کوڈ درج کریں:</label>
                <input type="text" id="otp_code" placeholder="1234">
                <button id="verifyBtn" onclick="verifyOtp()">ویریفائی (Verify)</button>
            </div>
        </div>

        <label>ٹرمینل ویو (Logs):</label>
        <div id="terminal"></div>
    </div>

    <script>
        let verifyUrl = "";
        let currentDeviceId = ""; 

        function log(msg, type='info') {
            const term = document.getElementById('terminal');
            const line = document.createElement('div');
            line.className = 'log-line log-' + type;
            line.innerHTML = msg;
            term.appendChild(line);
            term.scrollTop = term.scrollHeight;
        }

        async function startProcess() {
            const phone = document.getElementById('phone_number').value;
            if(!phone) { alert("نمبر لکھیں!"); return; }

            document.getElementById('startBtn').disabled = true;
            log(">>> سسٹم اسٹارٹ ہو رہا ہے...", 'info');

            const response = await fetch(`/stream_step1?phone=${phone}`);
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                const text = decoder.decode(value);
                const lines = text.split('\\n');
                
                for (const line of lines) {
                    if (line.startsWith('DATA:')) {
                        try {
                            const data = JSON.parse(line.replace('DATA:', ''));
                            if (data.type === 'log') {
                                log(data.message, data.style);
                            } else if (data.type === 'otp_needed') {
                                log(">>> OTP بھیج دیا گیا ہے۔ برائے مہربانی کوڈ درج کریں۔", 'success');
                                document.getElementById('otpSection').classList.remove('hidden');
                                verifyUrl = data.verify_url;
                                currentDeviceId = data.device_id; 
                            } else if (data.type === 'error') {
                                log("ERROR: " + data.message, 'error');
                                document.getElementById('startBtn').disabled = false;
                            }
                        } catch (e) {}
                    }
                }
            }
        }

        async function verifyOtp() {
            const otp = document.getElementById('otp_code').value;
            if(!otp) { alert("OTP لکھیں!"); return; }

            document.getElementById('verifyBtn').disabled = true;
            log(">>> OTP ویریفائی کیا جا رہا ہے...", 'info');

            const response = await fetch(`/stream_step2?otp=${otp}&verify_url=${encodeURIComponent(verifyUrl)}&device_id=${encodeURIComponent(currentDeviceId)}`);
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                const text = decoder.decode(value);
                const lines = text.split('\\n');
                
                for (const line of lines) {
                    if (line.startsWith('DATA:')) {
                        try {
                            const data = JSON.parse(line.replace('DATA:', ''));
                            if (data.type === 'log') {
                                log(data.message, data.style);
                            } else if (data.type === 'finished') {
                                log(">>> تمام پروسیس مکمل ہو گیا ہے۔", 'success');
                            }
                        } catch (e) {}
                    }
                }
            }
        }
    </script>
</body>
</html>
"""

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def get_random_device_id():
    random_hex = uuid.uuid4().hex
    return f"web-{random_hex}"

def send_log(message, style='info'):
    return f"DATA:{json.dumps({'type': 'log', 'message': message, 'style': style})}\n"

# A minimal valid JPEG image (1x1 pixel) for testing upload
def get_test_image():
    return b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xdb\x00C\x01\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x03\x01"\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x15\x00\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xc4\x00\x14\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xc4\x00\x14\x11\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00?\x00\xb2\xc0\x07\xff\xd9'

# Global Session
session = requests.Session()

common_headers = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Linux"',
    'Upgrade-Insecure-Requests': '1'
}
session.headers.update(common_headers)

# ==========================================
# STEP 1: SELENIUM -> FIND ID -> OTP API
# ==========================================
def process_step_1(phone_number):
    try:
        device_id = None
        
        yield send_log("1. Selenium Browser (Railway Mode) Start کیا جا رہا ہے...")
        
        chrome_options = Options()
        chrome_options.add_argument("--headless=new") 
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument(f"user-agent={common_headers['User-Agent']}")
        
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        
        target_url = "https://cloud.jazzdrive.com.pk"
        yield send_log(f"2. URL اوپن کیا جا رہا ہے: {target_url}")
        
        driver.get(target_url)
        
        found_id = False
        signup_url = ""
        max_retries = 20
        
        yield send_log("3. ری ڈائریکٹس ٹریک کیے جا رہے ہیں...")
        
        for i in range(max_retries):
            current_url = driver.current_url
            
            cookies = driver.get_cookies()
            for cookie in cookies:
                if 'device' in cookie['name'].lower() or 'deviceid' in cookie['name'].lower():
                    device_id = cookie['value']
                    yield send_log(f"✔ Device ID Found in Cookies: {device_id}", 'success')
            
            if "signup.php" in current_url and "id=" in current_url:
                signup_url = current_url
                found_id = True
                yield send_log("✔ سائن اپ آئی ڈی مل گئی!", 'success')
                break
            
            time.sleep(1)
        
        if not device_id:
            device_id = get_random_device_id()
            yield send_log(f"⚠ Device ID نہیں ملی، رینڈم جنریٹ کر دی: {device_id}", 'info')
        
        yield send_log("4. سیشن کوکیز منتقل کی جا رہی ہیں...")
        for cookie in driver.get_cookies():
            session.cookies.set(cookie['name'], cookie['value'])
            
        driver.quit()
        
        if not found_id:
            yield f"DATA:{json.dumps({'type': 'error', 'message': 'سائن اپ لنک نہیں ملا۔'})}\n"
            return

        yield send_log(f"5. API Call: OTP بھیجا جا رہا ہے...")
        yield send_log(f"   URL: {signup_url}", 'header')
        
        payload = {'enrichment_status': '', 'msisdn': phone_number}
        
        resp = session.post(signup_url, data=payload, allow_redirects=True)
        
        verify_url = resp.url
        yield send_log(f"   Status Code: {resp.status_code}")
        
        if "verify.php" in verify_url:
            yield send_log(f"✔ کامیابی سے Verify پیج پر پہنچ گئے: {verify_url}", 'success')
            yield f"DATA:{json.dumps({'type': 'otp_needed', 'verify_url': verify_url, 'device_id': device_id})}\n"
        else:
            yield send_log(f"❌ غلط ری ڈائریکٹ: {verify_url}", 'error')
            yield f"DATA:{json.dumps({'type': 'error', 'message': 'OTP Page پر نہیں جا سکا۔'})}\n"

    except Exception as e:
        yield f"DATA:{json.dumps({'type': 'error', 'message': str(e)})}\n"

# ==========================================
# STEP 2: VERIFY -> TOKEN -> UPLOAD (FIXED)
# ==========================================
def process_step_2(otp, verify_url, device_id):
    try:
        session.headers['X-deviceid'] = device_id
        
        yield send_log(f"6. API Call: OTP ویریفائی کر رہے ہیں...")
        
        payload = {'otp': otp}
        resp = session.post(verify_url, data=payload, allow_redirects=True)
        
        final_url = resp.url
        yield send_log(f"   Status: {resp.status_code}")
        
        parsed = urlparse(final_url)
        qs = parse_qs(parsed.query)
        
        if 'code' not in qs:
             yield f"DATA:{json.dumps({'type': 'error', 'message': 'Code نہیں ملا۔ OTP ایکسپائر یا غلط ہے۔'})}\n"
             return
             
        auth_code = qs['code'][0]
        yield send_log(f"✔ Auth Code: {auth_code}", 'success')
        
        yield send_log("7. ٹوکن جنریٹ کیا جا رہا ہے (Login)...")
        sapi_url = "https://cloud.jazzdrive.com.pk/sapi/login/oauth"
        params = {
            'action': 'login', 'platform': 'web', 
            'keytype': 'authorizationcode', 'key': auth_code
        }
        
        headers = session.headers.copy()
        headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
        
        resp_login = session.get(sapi_url, params=params, headers=headers)
        
        try:
            login_json = resp_login.json()
        except:
            yield send_log("Login JSON Error: " + resp_login.text, 'error')
            return

        if 'data' in login_json and 'validationkey' in login_json['data']:
            val_key = login_json['data']['validationkey']
            new_jsession = login_json['data'].get('jsessionid')
            
            yield send_log(f"✔ Validation Key: {val_key}", 'success')
            yield send_log(f"✔ New Session ID: {new_jsession}", 'info')
            
            # --- HEADERS ---
            cookie_string = f"JSESSIONID={new_jsession}; validationKey={val_key}; analyticsEnabled=true; cookiesWithPreferencesAccepted=true; cookiesAnalyticsAccepted=true"
            
            base_headers = {
                'Host': 'cloud.jazzdrive.com.pk',
                'Connection': 'keep-alive',
                'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
                'sec-ch-ua-platform': '"Linux"',
                'sec-ch-ua-mobile': '?0',
                'User-Agent': common_headers['User-Agent'],
                'X-deviceid': device_id,
                'Accept': '*/*',
                'Origin': 'https://cloud.jazzdrive.com.pk',
                'Referer': 'https://cloud.jazzdrive.com.pk/',
                'Cookie': cookie_string
            }

            # 7.5 Warmup
            yield send_log("7.5. سیشن Warm-up...", 'info')
            requests.get("https://cloud.jazzdrive.com.pk/sapi/system/information", 
                         params={'action': 'get', 'validationkey': val_key}, headers=base_headers)
            requests.get("https://cloud.jazzdrive.com.pk/sapi/profile", 
                         params={'action': 'get', 'validationkey': val_key}, headers=base_headers)
            
            # 8. UPLOAD (FIXED)
            yield send_log("8. فائل اپلوڈ ٹیسٹ شروع (Correct Data Field)...", 'header')
            upload_url = "https://cloud.jazzdrive.com.pk/sapi/upload"
            
            upload_params = {
                'action': 'save',
                'acceptasynchronous': 'true',
                'validationkey': val_key
            }
            
            image_bytes = get_test_image()
            filename = f"test_{int(time.time())}.jpg"
            
            # --- FIX HERE: Separate Files and Data ---
            # 'file' key for the binary
            multipart_files = {
                'file': (filename, image_bytes, 'image/jpeg')
            }
            
            # 'data' key for the JSON string (THIS IS WHAT COM-1013 WAS MISSING)
            metadata_struct = {
                "name": filename,
                "size": len(image_bytes),
                "modificationdate": "20260115T180000Z",
                "contenttype": "image/jpeg"
            }
            
            multipart_data = {
                'data': json.dumps(metadata_struct)
            }
            
            # Header copy WITHOUT Content-Type (requests adds boundary)
            upload_headers = base_headers.copy()
            if 'Content-Type' in upload_headers:
                del upload_headers['Content-Type']

            resp_upload = requests.post(
                upload_url, 
                params=upload_params, 
                files=multipart_files, # File binary here
                data=multipart_data,   # JSON 'data' field here
                headers=upload_headers
            )
            
            yield send_log("---------------- UPLOAD RESPONSE ----------------", 'header')
            yield send_log(resp_upload.text, 'info')
            
            if '"success":"Media uploaded successfully"' in resp_upload.text:
                 yield send_log("✅ مبارک ہو! فائل کامیابی سے اپلوڈ ہو گئی۔", 'success')
            else:
                 yield send_log("⚠️ اپلوڈ میں مسئلہ ہے، رسپانس چیک کریں۔", 'error')
            
            yield f"DATA:{json.dumps({'type': 'finished'})}\n"
            
        else:
            yield send_log("Login Failed: " + str(login_json), 'error')

    except Exception as e:
        yield f"DATA:{json.dumps({'type': 'error', 'message': str(e)})}\n"

# ==========================================
# FLASK ROUTES
# ==========================================
@app.route('/')
def index():
    return render_template_string(HTML_CODE)

@app.route('/stream_step1')
def stream_step1():
    phone = request.args.get('phone')
    return Response(stream_with_context(process_step_1(phone)), mimetype='text/plain')

@app.route('/stream_step2')
def stream_step2():
    otp = request.args.get('otp')
    verify_url = request.args.get('verify_url')
    device_id = request.args.get('device_id')
    return Response(stream_with_context(process_step_2(otp, verify_url, device_id)), mimetype='text/plain')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
