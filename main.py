import time
import json
import requests
import uuid
import os
import io
import datetime
import mimetypes
from flask import Flask, Response, request, render_template_string, stream_with_context
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)

# ==========================================
# HTML TEMPLATE (Frontend)
# ==========================================
HTML_CODE = """
<!DOCTYPE html>
<html lang="ur" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jazz Drive - Custom Upload</title>
    <style>
        body { background-color: #1e1e1e; color: #fff; font-family: 'Courier New', monospace; margin: 0; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { text-align: center; color: #00ff00; }
        .control-panel { background: #2d2d2d; padding: 20px; border-radius: 10px; margin-bottom: 20px; border: 1px solid #444; }
        input[type="text"], input[type="file"] { width: 100%; padding: 10px; margin: 10px 0; background: #444; border: 1px solid #666; color: #fff; border-radius: 5px; font-size: 16px; }
        button { width: 100%; padding: 12px; background: #007bff; border: none; color: white; border-radius: 5px; cursor: pointer; font-size: 16px; font-weight: bold; margin-top: 5px;}
        button:hover { background: #0056b3; }
        button:disabled { background: #555; cursor: not-allowed; }
        
        #terminal { 
            background-color: #000; 
            border: 2px solid #00ff00; 
            padding: 15px; 
            height: 500px; 
            overflow-y: scroll; 
            white-space: pre-wrap; 
            font-size: 13px; 
            border-radius: 5px;
            box-shadow: 0 0 15px rgba(0, 255, 0, 0.2);
        }
        .log-line { margin: 2px 0; border-bottom: 1px solid #333; padding-bottom: 2px; }
        .log-info { color: #00ffff; }
        .log-success { color: #00ff00; }
        .log-error { color: #ff4444; }
        .log-raw { color: #ff00ff; font-size: 11px; } 
        .log-header { color: #ffff00; font-size: 14px; font-weight: bold; margin-top: 15px; display: block; border-bottom: 1px dashed #ffff00; }
        .log-link { color: #ffff00; font-weight: bold; text-decoration: underline; word-break: break-all; font-size: 16px; }
        .hidden { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Jazz Drive Custom Uploader</h1>
        
        <div class="control-panel">
            <div id="step1">
                <label>موبائل نمبر (0300...):</label>
                <input type="text" id="phone_number" placeholder="030XXXXXXX">
                <button id="startBtn" onclick="startProcess()">اسٹارٹ (Start)</button>
            </div>
            
            <div id="otpSection" class="hidden">
                <label>OTP کوڈ درج کریں:</label>
                <input type="text" id="otp_code" placeholder="1234">
                <button id="verifyBtn" onclick="verifyOtp()">ویریفائی (Verify)</button>
            </div>

            <div id="uploadSection" class="hidden">
                <label style="color: #00ff00; font-weight:bold;">فائل منتخب کریں (Image, Video, Zip):</label>
                <input type="file" id="userFile">
                <button id="uploadBtn" onclick="uploadUserFile()">اپلوڈ اور شیئر (Upload & Share)</button>
            </div>
        </div>

        <label>ٹرمینل ویو (Logs):</label>
        <div id="terminal"></div>
    </div>

    <script>
        // Global variables to store session data
        let verifyUrl = "";
        let currentDeviceId = ""; 
        let authSession = {}; // Stores validationKey and cookies

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
            readStream(response);
        }

        async function verifyOtp() {
            const otp = document.getElementById('otp_code').value;
            if(!otp) { alert("OTP لکھیں!"); return; }

            document.getElementById('verifyBtn').disabled = true;
            log(">>> OTP ویریفائی اور لاگ ان کیا جا رہا ہے...", 'info');

            const response = await fetch(`/stream_step2?otp=${otp}&verify_url=${encodeURIComponent(verifyUrl)}&device_id=${encodeURIComponent(currentDeviceId)}`);
            readStream(response);
        }

        async function uploadUserFile() {
            const fileInput = document.getElementById('userFile');
            if(fileInput.files.length === 0) { alert("کوئی فائل منتخب نہیں کی!"); return; }

            document.getElementById('uploadBtn').disabled = true;
            log(">>> فائل اپلوڈ شروع ہو رہی ہے...", 'info');

            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            formData.append('validationKey', authSession.validationKey);
            formData.append('cookieString', authSession.cookieString);
            formData.append('deviceId', currentDeviceId);

            const response = await fetch('/stream_upload', {
                method: 'POST',
                body: formData
            });
            readStream(response);
        }

        async function readStream(response) {
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
                            } 
                            else if (data.type === 'otp_needed') {
                                log(">>> OTP بھیج دیا گیا ہے۔", 'success');
                                document.getElementById('otpSection').classList.remove('hidden');
                                verifyUrl = data.verify_url;
                                currentDeviceId = data.device_id; 
                            } 
                            else if (data.type === 'auth_success') {
                                log(">>> لاگ ان کامیاب! اب فائل سلیکٹ کریں۔", 'success');
                                // Store tokens for next step
                                authSession = {
                                    validationKey: data.validationKey,
                                    cookieString: data.cookieString
                                };
                                document.getElementById('uploadSection').classList.remove('hidden');
                                document.getElementById('otpSection').classList.add('hidden');
                            }
                            else if (data.type === 'error') {
                                log("ERROR: " + data.message, 'error');
                                // Re-enable buttons if needed
                                if(document.getElementById('startBtn').disabled) document.getElementById('startBtn').disabled = false;
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

# Global Session
session = requests.Session()

common_headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'Upgrade-Insecure-Requests': '1'
}
session.headers.update(common_headers)

# ==========================================
# STEP 1: SELENIUM -> FIND ID -> OTP API
# ==========================================
def process_step_1(phone_number):
    try:
        device_id = None
        
        yield send_log("1. Selenium Browser Start...", 'info')
        
        chrome_options = Options()
        chrome_options.add_argument("--headless=new") 
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument(f"user-agent={common_headers['User-Agent']}")
        
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        
        target_url = "https://cloud.jazzdrive.com.pk"
        driver.get(target_url)
        
        found_id = False
        signup_url = ""
        max_retries = 20
        
        yield send_log("2. ٹریکنگ کوکیز & ID...", 'info')
        
        for i in range(max_retries):
            current_url = driver.current_url
            
            cookies = driver.get_cookies()
            for cookie in cookies:
                if 'device' in cookie['name'].lower() or 'deviceid' in cookie['name'].lower():
                    device_id = cookie['value']
            
            if "signup.php" in current_url and "id=" in current_url:
                signup_url = current_url
                found_id = True
                yield send_log("✔ سائن اپ لنک مل گیا۔", 'success')
                break
            
            time.sleep(1)
        
        if not device_id:
            device_id = get_random_device_id()
        
        # Sync cookies
        for cookie in driver.get_cookies():
            session.cookies.set(cookie['name'], cookie['value'])
            
        driver.quit()
        
        if not found_id:
            yield f"DATA:{json.dumps({'type': 'error', 'message': 'سائن اپ لنک نہیں ملا۔'})}\n"
            return

        yield send_log(f"3. OTP بھیجا جا رہا ہے...", 'info')
        
        session.headers['Referer'] = target_url
        payload = {'enrichment_status': '', 'msisdn': phone_number}
        
        try:
            resp = session.post(signup_url, data=payload, allow_redirects=True, timeout=45)
            verify_url = resp.url
            
            if "verify.php" in verify_url:
                yield send_log(f"✔ OTP سینڈ ہو گیا۔", 'success')
                yield f"DATA:{json.dumps({'type': 'otp_needed', 'verify_url': verify_url, 'device_id': device_id})}\n"
            else:
                yield send_log(f"❌ غلط ری ڈائریکٹ: {verify_url}", 'error')
                yield f"DATA:{json.dumps({'type': 'error', 'message': 'OTP Page پر نہیں جا سکا۔'})}\n"
        except requests.Timeout:
             yield f"DATA:{json.dumps({'type': 'error', 'message': 'TimeOut: سرور نے جواب نہیں دیا۔'})}\n"

    except Exception as e:
        yield f"DATA:{json.dumps({'type': 'error', 'message': str(e)})}\n"

# ==========================================
# STEP 2: VERIFY -> LOGIN ONLY (No Upload)
# ==========================================
def process_step_2_login(otp, verify_url, device_id):
    try:
        session.headers['X-deviceid'] = device_id
        
        yield send_log(f"4. OTP ویریفیکیشن...", 'info')
        
        payload = {'otp': otp}
        resp = session.post(verify_url, data=payload, allow_redirects=True, timeout=45)
        
        final_url = resp.url
        parsed = urlparse(final_url)
        qs = parse_qs(parsed.query)
        
        if 'code' not in qs:
             yield f"DATA:{json.dumps({'type': 'error', 'message': 'غلط OTP یا سیشن ایکسپائر۔'})}\n"
             return
             
        auth_code = qs['code'][0]
        yield send_log(f"✔ Auth Code موصول: {auth_code}", 'success')
        
        # SAPI LOGIN
        yield send_log("5. لاگ ان ٹوکن (Login SAPI)...", 'info')
        sapi_url = "https://cloud.jazzdrive.com.pk/sapi/login/oauth"
        params = {
            'action': 'login', 'platform': 'web', 
            'keytype': 'authorizationcode', 'key': auth_code
        }
        
        session.headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
        resp_login = session.get(sapi_url, params=params, timeout=45)
        
        login_json = resp_login.json()

        if 'data' in login_json and 'validationkey' in login_json['data']:
            val_key = login_json['data']['validationkey']
            new_jsession = login_json['data'].get('jsessionid')
            
            yield send_log(f"✔ لاگ ان کامیاب (ValKey: {val_key[:10]}...)", 'success')
            
            cookie_string = f"JSESSIONID={new_jsession}; validationKey={val_key}; analyticsEnabled=true; cookiesWithPreferencesAccepted=true; cookiesAnalyticsAccepted=true"
            
            # Send keys back to frontend
            yield f"DATA:{json.dumps({'type': 'auth_success', 'validationKey': val_key, 'cookieString': cookie_string})}\n"
            
        else:
            yield send_log("Login Failed: " + str(login_json), 'error')

    except Exception as e:
        yield f"DATA:{json.dumps({'type': 'error', 'message': str(e)})}\n"

# ==========================================
# STEP 3: CUSTOM UPLOAD HANDLER
# ==========================================
def process_custom_upload(file_storage, val_key, cookie_string, device_id):
    try:
        filename = file_storage.filename
        content_type = file_storage.content_type
        # Read file into memory (be careful with very large files on limited RAM)
        file_bytes = file_storage.read()
        file_size = len(file_bytes)
        
        yield send_log(f"----------------------------------------", 'header')
        yield send_log(f"6. فائل پروسیسنگ شروع: {filename}", 'header')
        yield send_log(f"   Size: {file_size} bytes | Type: {content_type}", 'info')

        # Manual Headers Setup
        manual_headers = {
            'Host': 'cloud.jazzdrive.com.pk',
            'Connection': 'keep-alive',
            'User-Agent': common_headers['User-Agent'],
            'X-deviceid': device_id,
            'Accept': '*/*',
            'Origin': 'https://cloud.jazzdrive.com.pk',
            'Referer': 'https://cloud.jazzdrive.com.pk/',
            'Cookie': cookie_string
        }

        # Warmup (Just to be safe)
        requests.get("https://cloud.jazzdrive.com.pk/sapi/system/information", 
                        params={'action': 'get', 'validationkey': val_key}, headers=manual_headers, timeout=30)

        # UPLOAD
        yield send_log(f"7. Jazz Drive پر اپلوڈ ہو رہا ہے...", 'info')
        upload_url = "https://cloud.jazzdrive.com.pk/sapi/upload"
        upload_params = {'action': 'save', 'acceptasynchronous': 'true', 'validationkey': val_key}
        
        # Correct Metadata Structure
        metadata_struct = {
            "data": {  
                "name": filename,
                "size": file_size,
                "modificationdate": datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"),
                "contenttype": content_type
            }
        }
        
        multipart_payload = {
            'data': (None, json.dumps(metadata_struct)), 
            'file': (filename, file_bytes, content_type)
        }

        resp_upload = requests.post(
            upload_url, 
            params=upload_params, 
            files=multipart_payload,
            headers=manual_headers, 
            timeout=300 # 5 min timeout for large files
        )
        
        uploaded_file_id = None
        if '"success":"Media uploaded successfully"' in resp_upload.text:
                yield send_log("✅ فائل کامیابی سے اپلوڈ ہو گئی!", 'success')
                try:
                    up_json = resp_upload.json()
                    if 'data' in up_json and 'id' in up_json['data']:
                        uploaded_file_id = up_json['data']['id']
                    else:
                        uploaded_file_id = up_json.get('id')
                    yield send_log(f"   File ID: {uploaded_file_id}", 'info')
                except: pass
        else:
                yield send_log("⚠️ اپلوڈ فیلڈ: " + resp_upload.text, 'error')
                return

        # SHARE
        if uploaded_file_id:
            yield send_log("8. شیئر لنک جنریٹ ہو رہا ہے...", 'header')
            share_url = "https://cloud.jazzdrive.com.pk/sapi/link" 
            share_params = {'action': 'create', 'validationkey': val_key}
            
            share_payload = {
                "data": {
                    "itemid": uploaded_file_id,
                    "permission": 20, 
                    "password": ""
                }
            }
            
            share_headers = manual_headers.copy()
            share_headers['Content-Type'] = 'application/json;charset=UTF-8'
            
            resp_share = requests.post(
                share_url,
                params=share_params,
                json=share_payload, 
                headers=share_headers,
                timeout=45
            )
            
            # --- RAW RESPONSE OUTPUT ---
            yield send_log("---- ORIGINAL API RESPONSE (RAW) ----", 'header')
            try:
                # Pretty print JSON if possible
                raw_json = json.dumps(resp_share.json(), indent=4, ensure_ascii=False)
                yield send_log(raw_json, 'raw') # Using a special color style
            except:
                yield send_log(resp_share.text, 'raw')
            yield send_log("-------------------------------------", 'header')
            # ---------------------------

            try:
                share_json = resp_share.json()
                public_url = None
                
                if 'data' in share_json and 'url' in share_json['data']:
                    public_url = share_json['data']['url']
                elif 'url' in share_json:
                    public_url = share_json['url']
                    
                if public_url:
                    yield send_log("🎉 FINAL LINK:", 'success')
                    yield send_log(f"<a href='{public_url}' target='_blank' class='log-link'>{public_url}</a>", 'success')
                else:
                    yield send_log(" لنک نہیں ملا۔", 'error')
            except: pass
        
        yield f"DATA:{json.dumps({'type': 'finished'})}\n"

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
    return Response(stream_with_context(process_step_2_login(otp, verify_url, device_id)), mimetype='text/plain')

@app.route('/stream_upload', methods=['POST'])
def stream_upload():
    if 'file' not in request.files:
        return "No file part"
    
    file = request.files['file']
    val_key = request.form['validationKey']
    cookie_string = request.form['cookieString']
    device_id = request.form['deviceId']
    
    return Response(stream_with_context(process_custom_upload(file, val_key, cookie_string, device_id)), mimetype='text/plain')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
