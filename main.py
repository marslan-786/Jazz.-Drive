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
from werkzeug.datastructures import FileStorage

app = Flask(__name__)

# ==========================================
# CONFIGURATION
# ==========================================
SESSION_DIR = 'user_sessions'
if not os.path.exists(SESSION_DIR):
    os.makedirs(SESSION_DIR)

# 1 Hour Timeout for massive uploads
UPLOAD_TIMEOUT = 3600 

COMMON_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Linux"',
    'Upgrade-Insecure-Requests': '1',
    'Accept-Language': 'en-US,en;q=0.9,ur-PK;q=0.8,ur;q=0.7'
}

# --- HELPER FUNCTIONS ---
def save_session(custom_id, data):
    try:
        with open(os.path.join(SESSION_DIR, f"{custom_id}.json"), 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving session: {e}")

def load_session(custom_id):
    path = os.path.join(SESSION_DIR, f"{custom_id}.json")
    if os.path.exists(path):
        try:
            with open(path, 'r') as f: return json.load(f)
        except: return None
    return None

def delete_session(custom_id):
    try: os.remove(os.path.join(SESSION_DIR, f"{custom_id}.json"))
    except: pass

def get_chrome_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    # New isolated driver for every request
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def get_random_device_id():
    return f"web-{uuid.uuid4().hex}"

@app.route('/api', methods=['GET', 'POST'])
def unified_api():
    custom_id = request.args.get('id')
    if not custom_id: return jsonify({"status": "error", "message": "ID required"}), 400

    # ----------------------------------------------------------------
    # 1. GENERATE OTP
    # ----------------------------------------------------------------
    if request.method == 'GET' and request.args.get('gen-otp'):
        phone = request.args.get('gen-otp')
        driver = None
        try:
            driver = get_chrome_driver()
            driver.get("https://cloud.jazzdrive.com.pk")
            
            signup_url, device_id = "", None
            # Wait loop specifically for ID generation
            for _ in range(20):
                if "signup.php" in driver.current_url:
                    signup_url = driver.current_url
                    for c in driver.get_cookies():
                        if 'device' in c['name'].lower(): device_id = c['value']
                    break
                time.sleep(0.5)
            
            if not device_id: device_id = get_random_device_id()
            cookies = {c['name']: c['value'] for c in driver.get_cookies()}
            
            # Important: Close driver immediately to free RAM
            driver.quit()
            driver = None 
            
            if not signup_url: return jsonify({"status": "error", "message": "Signup URL not found via Selenium"}), 500

            session = requests.Session()
            session.headers.update(COMMON_HEADERS)
            session.cookies.update(cookies)
            
            resp = session.post(signup_url, data={'enrichment_status': '', 'msisdn': phone}, timeout=30)
            
            if "verify.php" in resp.url:
                save_session(custom_id, {
                    "step": "otp_sent", "verify_url": resp.url, 
                    "device_id": device_id, "cookies": session.cookies.get_dict()
                })
                return jsonify({"status": "success", "message": "OTP Sent", "next_action": "verify-otp"})
            return jsonify({"status": "error", "message": "Failed to get OTP from Jazz"}), 400
        except Exception as e:
            if driver: driver.quit()
            return jsonify({"status": "error", "message": str(e)}), 500

    # ----------------------------------------------------------------
    # 2. VERIFY OTP
    # ----------------------------------------------------------------
    elif request.method == 'GET' and request.args.get('verify-otp'):
        otp = request.args.get('verify-otp')
        state = load_session(custom_id)
        if not state: return jsonify({"status": "error", "message": "Session not found"}), 404

        try:
            session = requests.Session()
            session.headers.update(COMMON_HEADERS)
            session.headers['X-deviceid'] = state['device_id']
            session.cookies.update(state['cookies'])
            
            resp = session.post(state['verify_url'], data={'otp': otp}, timeout=45)
            qs = parse_qs(urlparse(resp.url).query)
            
            if 'code' not in qs: return jsonify({"status": "error", "message": "Invalid OTP Code"}), 400
            
            # SAPI Login
            session.headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
            resp_login = session.get("https://cloud.jazzdrive.com.pk/sapi/login/oauth", 
                                   params={'action': 'login', 'platform': 'web', 'keytype': 'authorizationcode', 'key': qs['code'][0]},
                                   timeout=45)
            
            data = resp_login.json().get('data', {})
            if 'validationkey' in data:
                jsession = data.get('jsessionid')
                val_key = data.get('validationkey')
                state.update({
                    "step": "authenticated", "validation_key": val_key,
                    "cookie_string": f"JSESSIONID={jsession}; validationKey={val_key}; analyticsEnabled=true; cookiesWithPreferencesAccepted=true; cookiesAnalyticsAccepted=true"
                })
                save_session(custom_id, state)
                return jsonify({"status": "success", "message": "Verified"})
            return jsonify({"status": "error", "message": "Login Failed (SAPI)"}), 400
        except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

    # ----------------------------------------------------------------
    # 3. UPLOAD & SHARE (STREAMING MODE - NO RAM CRASH)
    # ----------------------------------------------------------------
    elif request.method == 'POST':
        if 'file' not in request.files: return jsonify({"status": "error", "message": "No file"}), 400
        state = load_session(custom_id)
        if not state or state.get('step') != 'authenticated': return jsonify({"status": "error", "message": "Not authenticated"}), 401

        file_obj = request.files['file']
        val_key = state['validation_key']
        
        headers = {
            'Host': 'cloud.jazzdrive.com.pk',
            'Connection': 'keep-alive',
            'User-Agent': COMMON_HEADERS['User-Agent'],
            'X-deviceid': state['device_id'],
            'Origin': 'https://cloud.jazzdrive.com.pk',
            'Referer': 'https://cloud.jazzdrive.com.pk/',
            'Cookie': state['cookie_string'],
            'sec-ch-ua-platform': '"Linux"',
            'Accept': '*/*'
        }

        try:
            # 3.1 Pre-Check
            requests.get("https://cloud.jazzdrive.com.pk/sapi/profile/changes", 
                         params={'action': 'get', 'from': int(time.time()*1000), 'origin': 'omh,dropbox', 'locked': 'true', 'validationkey': val_key}, headers=headers, timeout=30)

            # 3.2 UPLOAD (STREAMING)
            # We determine file size without reading content if possible
            file_obj.seek(0, os.SEEK_END)
            file_size = file_obj.tell()
            file_obj.seek(0)
            
            metadata = {
                "data": {
                    "name": file_obj.filename,
                    "size": file_size,
                    "modificationdate": datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"),
                    "contenttype": file_obj.content_type
                }
            }
            
            # CRITICAL CHANGE: Pass file object's stream directly. DO NOT READ()
            files_payload = {
                'data': (None, json.dumps(metadata)), 
                'file': (file_obj.filename, file_obj.stream, file_obj.content_type)
            }
            
            resp_up = requests.post("https://cloud.jazzdrive.com.pk/sapi/upload", 
                                  params={'action': 'save', 'acceptasynchronous': 'true', 'validationkey': val_key},
                                  files=files_payload, 
                                  headers=headers, 
                                  timeout=UPLOAD_TIMEOUT) # 1 Hour Timeout

            uploaded_id = None
            try:
                up_json = resp_up.json()
                if 'metadata' in up_json and 'files' in up_json['metadata']: uploaded_id = up_json['metadata']['files'][0]['id']
                elif 'id' in up_json: uploaded_id = up_json['id']
            except: pass

            if not uploaded_id:
                return jsonify({"status": "error", "message": "Upload failed", "debug": resp_up.text[:300]})

            # 3.3 Intermediate Requests (To verify file exists on server)
            json_headers = headers.copy()
            json_headers['Content-Type'] = 'application/json;charset=UTF-8'
            
            requests.post("https://cloud.jazzdrive.com.pk/sapi/media",
                          params={'action': 'get', 'origin': 'omh,dropbox', 'validationkey': val_key},
                          json={"data":{"ids":[uploaded_id],"fields":["creationdate","url","shared","uploaded"]}},
                          headers=json_headers, timeout=45)

            # 3.4 SHARE
            resp_share = requests.post("https://cloud.jazzdrive.com.pk/sapi/media/set", 
                                     params={'action': 'save', 'validationkey': val_key},
                                     json={"data":{"set":{"items":[uploaded_id]}}}, 
                                     headers=json_headers, timeout=45)
            
            final_link = "Not Generated"
            try:
                share_json = resp_share.json()
                if 'url' in share_json: final_link = share_json['url']
                elif 'data' in share_json and 'url' in share_json['data']: final_link = share_json['data']['url']
            except: pass

            delete_session(custom_id)

            return jsonify({
                "status": "success",
                "file_id": uploaded_id,
                "share_link": final_link,
                "file_size": file_size
            })

        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "error", "message": "Invalid Action"}), 400

if __name__ == '__main__':
    # Threaded=True is vital for concurrency
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), threaded=True)
