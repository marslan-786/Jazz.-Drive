import time
import json
import requests
import uuid
import os
import datetime
import mimetypes
import threading  # ✅ Added for Keep-Alive
from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)

# ==========================================
# CONFIGURATION
# ==========================================
SESSION_DIR = 'user_sessions'
if not os.path.exists(SESSION_DIR):
    os.makedirs(SESSION_DIR)

# 1 Hour Timeout
UPLOAD_TIMEOUT = 3600 

COMMON_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Linux"',
    'Upgrade-Insecure-Requests': '1',
    'Accept-Language': 'en-US,en;q=0.9,ur-PK;q=0.8,ur;q=0.7'
}

def save_session(custom_id, data):
    try:
        with open(os.path.join(SESSION_DIR, f"{custom_id}.json"), 'w') as f:
            json.dump(data, f, indent=4)
    except: pass

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
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def get_random_device_id():
    return f"web-{uuid.uuid4().hex}"

# 💓 KEEP-ALIVE WORKER (NEW)
# 💓 KEEP-ALIVE WORKER
def keep_session_alive(val_key, headers, stop_event):
    """
    یہ فنکشن بیک گراؤنڈ میں ہر 10 سیکنڈ بعد سرور کو پنگ کرے گا
    تاکہ سیشن ایکسپائر نہ ہو۔
    """
    while not stop_event.is_set():
        try:
            # 1. Profile Check
            requests.get("https://cloud.jazzdrive.com.pk/sapi/profile/changes", 
                         params={'action': 'get', 'from': int(time.time()*1000), 'origin': 'omh,dropbox', 'locked': 'true', 'validationkey': val_key},
                         headers=headers, timeout=10)
            
            # 👇 تبدیلی یہاں کرنی ہے (40 کی جگہ 10)
            if stop_event.wait(10): break 
            
            # 2. Storage Check (Alternate Pings)
            requests.get("https://cloud.jazzdrive.com.pk/sapi/media",
                         params={'action': 'get-storage-space', 'softdeleted': 'true', 'validationkey': val_key},
                         headers=headers, timeout=10)
            
            # 👇 تبدیلی یہاں کرنی ہے (40 کی جگہ 10)
            if stop_event.wait(10): break
            
        except Exception as e:
            print(f"Keep-Alive Error: {e}")
            # اگر ایرر آئے تو تھوڑا رک کر دوبارہ کوشش کریں
            if stop_event.wait(5): break

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
            for _ in range(20):
                if "signup.php" in driver.current_url:
                    signup_url = driver.current_url
                    for c in driver.get_cookies():
                        if 'device' in c['name'].lower(): device_id = c['value']
                    break
                time.sleep(0.5)
            
            if not device_id: device_id = get_random_device_id()
            cookies = {c['name']: c['value'] for c in driver.get_cookies()}
            driver.quit()
            
            if not signup_url: return jsonify({"status": "error", "message": "Signup URL not found"}), 500

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
            return jsonify({"status": "error", "message": "Failed to get OTP"}), 400
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
            
            if 'code' not in qs: return jsonify({"status": "error", "message": "Invalid OTP"}), 400
            
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
            return jsonify({"status": "error", "message": "Login Failed"}), 400
        except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

    # ----------------------------------------------------------------
    # 3. UPLOAD & SHARE (WITH KEEP-ALIVE SYSTEM)
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

        # Thread Controller
        stop_alive = threading.Event()
        alive_thread = None

        try:
            # 3.1 Pre-Check
            requests.get("https://cloud.jazzdrive.com.pk/sapi/profile/changes", 
                         params={'action': 'get', 'from': int(time.time()*1000), 'origin': 'omh,dropbox', 'locked': 'true', 'validationkey': val_key}, headers=headers, timeout=30)

            # 3.2 START KEEP-ALIVE THREAD (The Fix 🚀)
            alive_thread = threading.Thread(target=keep_session_alive, args=(val_key, headers, stop_alive))
            alive_thread.daemon = True # اگر مین پروگرام بند ہو تو یہ بھی بند ہو جائے
            alive_thread.start()

            # 3.3 UPLOAD (BLOCKING)
            file_obj.seek(0, os.SEEK_END)
            file_size = file_obj.tell()
            file_obj.seek(0)
            
            mime_type, _ = mimetypes.guess_type(file_obj.filename)
            if not mime_type: mime_type = "application/octet-stream"
            if file_obj.filename.lower().endswith('.js'): mime_type = 'text/javascript'
            if file_obj.filename.lower().endswith('.bak'): mime_type = 'application/x-trash'

            metadata = {
                "data": {
                    "name": file_obj.filename,
                    "size": file_size,
                    "modificationdate": datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"),
                    "contenttype": mime_type
                }
            }
            
            files_payload = {
                'data': (None, json.dumps(metadata)), 
                'file': (file_obj.filename, file_obj.stream, mime_type)
            }
            
            # اپلوڈ کے دوران اب بیک گراؤنڈ تھریڈ چلتا رہے گا
            resp_up = requests.post("https://cloud.jazzdrive.com.pk/sapi/upload", 
                                  params={'action': 'save', 'acceptasynchronous': 'true', 'validationkey': val_key},
                                  files=files_payload, 
                                  headers=headers, 
                                  timeout=UPLOAD_TIMEOUT)

            # اپلوڈ ختم، تھریڈ روک دیں
            stop_alive.set()
            if alive_thread: alive_thread.join()

            uploaded_id = None
            try:
                up_json = resp_up.json()
                if 'metadata' in up_json and 'files' in up_json['metadata']: uploaded_id = up_json['metadata']['files'][0]['id']
                elif 'id' in up_json: uploaded_id = up_json['id']
            except: pass

            if not uploaded_id:
                return jsonify({"status": "error", "message": "Upload failed", "debug": resp_up.text[:300]})

            # 3.4 Intermediate Requests
            json_headers = headers.copy()
            json_headers['Content-Type'] = 'application/json;charset=UTF-8'
            
            requests.post("https://cloud.jazzdrive.com.pk/sapi/media",
                          params={'action': 'get', 'origin': 'omh,dropbox', 'validationkey': val_key},
                          json={"data":{"ids":[uploaded_id],"fields":["creationdate","postingdate","name","size","thumbnails","viewurl","url","videometadata","audiometadata","shared","exported","favorite","origin","folderid","labels","modificationdate","uploadeddeviceid","uploaded","etag"]}},
                          headers=json_headers, timeout=45)

            # 3.5 SHARE
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
                "file_size_mb": round(file_size/(1024*1024), 2),
                "detected_mime": mime_type
            })

        except Exception as e:
            # ایرر کی صورت میں تھریڈ لازمی بند کریں
            stop_alive.set()
            if alive_thread: alive_thread.join()
            return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "error", "message": "Invalid Action"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), threaded=True)
