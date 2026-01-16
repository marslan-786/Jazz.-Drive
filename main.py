import time
import json
import requests
import uuid
import os
import datetime
from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)

# ==========================================
# CONFIGURATION & STORAGE
# ==========================================
SESSION_DIR = 'user_sessions'
if not os.path.exists(SESSION_DIR):
    os.makedirs(SESSION_DIR)

COMMON_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'Upgrade-Insecure-Requests': '1'
}

# --- HELPER FUNCTIONS ---
def save_session(custom_id, data):
    file_path = os.path.join(SESSION_DIR, f"{custom_id}.json")
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

def load_session(custom_id):
    file_path = os.path.join(SESSION_DIR, f"{custom_id}.json")
    if not os.path.exists(file_path):
        return None
    with open(file_path, 'r') as f:
        return json.load(f)

def delete_session(custom_id):
    file_path = os.path.join(SESSION_DIR, f"{custom_id}.json")
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except: pass

def get_chrome_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    return driver

def get_random_device_id():
    return f"web-{uuid.uuid4().hex}"

# ==========================================
# UNIFIED API ROUTE (/api)
# ==========================================
@app.route('/api', methods=['GET', 'POST'])
def unified_api():
    custom_id = request.args.get('id')
    
    if not custom_id:
        return jsonify({"status": "error", "message": "ID parameter is required"}), 400

    # ---------------------------------------------------------
    # ACTION 1: GENERATE OTP (GET)
    # ---------------------------------------------------------
    if request.method == 'GET' and request.args.get('gen-otp'):
        phone_number = request.args.get('gen-otp')
        driver = None
        try:
            driver = get_chrome_driver()
            target_url = "https://cloud.jazzdrive.com.pk"
            driver.get(target_url)
            
            signup_url, device_id, found_id = "", None, False
            
            for i in range(15):
                if "signup.php" in driver.current_url and "id=" in driver.current_url:
                    signup_url = driver.current_url
                    found_id = True
                    for cookie in driver.get_cookies():
                        if 'device' in cookie['name'].lower():
                            device_id = cookie['value']
                    break
                time.sleep(1)
            
            if not device_id: device_id = get_random_device_id()
            cookies_dict = {c['name']: c['value'] for c in driver.get_cookies()}
            driver.quit()
            
            if not found_id:
                return jsonify({"status": "error", "message": "Signup URL not found"}), 500

            session = requests.Session()
            session.headers.update(COMMON_HEADERS)
            session.cookies.update(cookies_dict)
            session.headers['Referer'] = target_url
            
            resp = session.post(signup_url, data={'enrichment_status': '', 'msisdn': phone_number}, timeout=30)
            verify_url = resp.url
            
            if "verify.php" in verify_url:
                state_data = {
                    "step": "otp_sent",
                    "verify_url": verify_url,
                    "device_id": device_id,
                    "cookies": session.cookies.get_dict(),
                    "timestamp": str(datetime.datetime.now())
                }
                save_session(custom_id, state_data)
                return jsonify({"status": "success", "message": "OTP Sent", "next_action": "verify-otp"})
            else:
                return jsonify({"status": "error", "message": "Failed to reach verify page"}), 400

        except Exception as e:
            if driver: driver.quit()
            return jsonify({"status": "error", "message": str(e)}), 500

    # ---------------------------------------------------------
    # ACTION 2: VERIFY OTP (GET)
    # ---------------------------------------------------------
    elif request.method == 'GET' and request.args.get('verify-otp'):
        otp_code = request.args.get('verify-otp')
        state = load_session(custom_id)
        
        if not state:
            return jsonify({"status": "error", "message": "Session ID not found"}), 404
            
        try:
            session = requests.Session()
            session.headers.update(COMMON_HEADERS)
            session.headers['X-deviceid'] = state['device_id']
            session.cookies.update(state['cookies'])

            resp = session.post(state['verify_url'], data={'otp': otp_code}, allow_redirects=True, timeout=30)
            parsed = urlparse(resp.url)
            qs = parse_qs(parsed.query)
            
            if 'code' not in qs:
                return jsonify({"status": "error", "message": "Invalid OTP"}), 400
                
            auth_code = qs['code'][0]
            
            sapi_url = "https://cloud.jazzdrive.com.pk/sapi/login/oauth"
            params = {'action': 'login', 'platform': 'web', 'keytype': 'authorizationcode', 'key': auth_code}
            session.headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
            
            resp_login = session.get(sapi_url, params=params)
            login_json = resp_login.json()
            
            if 'data' in login_json and 'validationkey' in login_json['data']:
                val_key = login_json['data']['validationkey']
                jsession = login_json['data'].get('jsessionid')
                
                state['step'] = "authenticated"
                state['validation_key'] = val_key
                state['cookie_string'] = f"JSESSIONID={jsession}; validationKey={val_key}; analyticsEnabled=true; cookiesWithPreferencesAccepted=true; cookiesAnalyticsAccepted=true"
                save_session(custom_id, state)
                
                return jsonify({"status": "success", "message": "Verified. Ready to Upload."})
            else:
                 return jsonify({"status": "error", "message": "Login Failed"}), 400

        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    # ---------------------------------------------------------
    # ACTION 3: UPLOAD FILE & SHARE (POST) -- FIXED LOGIC
    # ---------------------------------------------------------
    elif request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file attached"}), 400

        state = load_session(custom_id)
        if not state or state.get('step') != 'authenticated':
             return jsonify({"status": "error", "message": "Session not authenticated"}), 401

        file = request.files['file']
        filename = file.filename
        file_bytes = file.read()
        
        headers = {
            'Host': 'cloud.jazzdrive.com.pk',
            'Connection': 'keep-alive',
            'User-Agent': COMMON_HEADERS['User-Agent'],
            'X-deviceid': state['device_id'],
            'Accept': '*/*',
            'Origin': 'https://cloud.jazzdrive.com.pk',
            'Referer': 'https://cloud.jazzdrive.com.pk/',
            'Cookie': state['cookie_string']
        }
        
        upload_url = "https://cloud.jazzdrive.com.pk/sapi/upload"
        metadata = {
            "data": {  
                "name": filename,
                "size": len(file_bytes),
                "modificationdate": datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"),
                "contenttype": file.content_type
            }
        }
        
        payload = {
            'data': (None, json.dumps(metadata)), 
            'file': (filename, file_bytes, file.content_type)
        }
        
        try:
            # 1. Perform Upload
            resp_upload = requests.post(
                upload_url, 
                params={'action': 'save', 'acceptasynchronous': 'true', 'validationkey': state['validation_key']}, 
                files=payload, 
                headers=headers, 
                timeout=300
            )
            
            # 2. Parse Upload Response CAREFULLY
            uploaded_id = None
            try:
                up_json = resp_upload.json()
                
                # CHECK 1: ID at Root (This matches your log)
                if 'id' in up_json:
                    uploaded_id = up_json['id']
                
                # CHECK 2: ID inside Data (Alternative format)
                elif 'data' in up_json and 'id' in up_json['data']:
                    uploaded_id = up_json['data']['id']
                    
            except:
                return jsonify({"status": "error", "message": "Invalid JSON response from server", "raw": resp_upload.text})

            # 3. If ID Found -> SHARE
            if uploaded_id:
                share_url = "https://cloud.jazzdrive.com.pk/sapi/link"
                share_payload = {"data": {"itemid": uploaded_id, "permission": 20, "password": ""}}
                share_headers = headers.copy()
                share_headers['Content-Type'] = 'application/json;charset=UTF-8'
                
                resp_share = requests.post(
                    share_url, 
                    params={'action': 'create', 'validationkey': state['validation_key']}, 
                    json=share_payload, 
                    headers=share_headers
                )
                
                share_data = {}
                try:
                    share_data = resp_share.json()
                except:
                    share_data = {"raw": resp_share.text}

                # SUCCESS: Delete Session & Return
                delete_session(custom_id)
                
                return jsonify({
                    "status": "success",
                    "file_id": uploaded_id,
                    "share_response": share_data
                })
            
            else:
                # Upload call worked but ID not found in JSON
                return jsonify({
                    "status": "error", 
                    "message": "Upload successful but ID not found", 
                    "server_response": resp_upload.text
                })

        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    else:
        return jsonify({"status": "error", "message": "Invalid Action"}), 400

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, threaded=True)
