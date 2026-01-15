import os
import uvicorn
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from playwright.sync_api import sync_playwright

app = FastAPI()

# --- Request Models ---
class LoginRequest(BaseModel):
    phone: str

class VerifyRequest(BaseModel):
    otp: str
    session_id: str

# --- Headers ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://jazzdrive.com.pk",
    "Referer": "https://jazzdrive.com.pk"
}

# --- 1. ID نکالنے اور نمبر بھیجنے والا فنکشن (Updated Logic) ---
@app.post("/send-otp")
def send_otp(data: LoginRequest):
    session_id = None
    print("Launching Browser to get Signup ID...")

    try:
        with sync_playwright() as p:
            # براؤزر کی سیٹنگز (میموری بچانے کے لیے)
            browser = p.chromium.launch(
                headless=True, 
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(user_agent=HEADERS["User-Agent"])
            page = context.new_page()
            
            # ٹائم آؤٹ کو بڑھا کر 60 سیکنڈ کر دیا ہے تاکہ 502 ایرر نہ آئے
            page.set_default_timeout(60000)

            try:
                # 1. کلاؤڈ لنک کھولیں
                print("Opening Cloud URL...")
                page.goto("https://cloud.jazzdrive.com.pk")
                
                # 2. یہاں آپ کی بتائی ہوئی لاجک: "Signup ID" کا انتظار کریں
                # ہم انتظار کریں گے کہ یو آر ایل میں "signup.php" یا صرف "id=" آ جائے
                print("Waiting for Signup ID redirect...")
                page.wait_for_url("**id=*", timeout=60000)
                
                final_url = page.url
                print(f"Landed on: {final_url}")
                
                if "id=" in final_url:
                    # ID نکالیں
                    session_id = final_url.split("id=")[1].split("&")[0]
                    print(f"Got Session ID: {session_id}")
                else:
                    print("URL found but ID missing.")

            except Exception as e:
                print(f"Browser Error: {e}")
                # اگر براؤزر ٹائم آؤٹ ہو جائے تو بھی کوشش کریں کہ اگر کوئی URL کھلا ہو تو ID نکال لیں
                try:
                    if "id=" in page.url:
                         session_id = page.url.split("id=")[1].split("&")[0]
                except:
                    pass
            finally:
                browser.close()

        if not session_id:
            raise HTTPException(status_code=500, detail="Could not extract Signup ID from Cloud URL.")

        # 3. اب اس ID کو استعمال کر کے نمبر بھیجیں
        print(f"Sending OTP to {data.phone} using ID: {session_id}")
        
        # یہاں signup.php استعمال ہو رہا ہے کیونکہ یہ پہلا سٹیپ ہے
        api_url = f"https://jazzdrive.com.pk/oauth2/signup.php?id={session_id}"
        
        payload = {
            "msisdn": data.phone, 
            "enrichment_status": ""
        }
        
        resp = requests.post(api_url, data=payload, headers=HEADERS)
        print(f"API Response Code: {resp.status_code}")
        
        if resp.status_code in [200, 302]:
            return {
                "status": "success",
                "message": "OTP Sent Successfully",
                "session_id": session_id,  # یہ ID سنبھال لیں، یہ ویریفائی میں کام آئے گی
                "debug_url": api_url
            }
        else:
            return {
                "status": "fail", 
                "message": "Failed to send OTP", 
                "response": resp.text
            }

    except Exception as e:
        print(f"Server Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- 2. OTP ویریفائی والا فنکشن (وہی پرانا، یہ ٹھیک ہے) ---
@app.post("/verify-otp")
def verify_otp(data: VerifyRequest):
    # نوٹ: کبھی کبھی لاگ ان کے وقت verify.php استعمال ہوتا ہے
    verify_url = f"https://jazzdrive.com.pk/verify.php?id={data.session_id}"
    payload = {"otp": data.otp}
    
    session = requests.Session()
    try:
        resp = session.post(verify_url, data=payload, headers=HEADERS, allow_redirects=False)
        
        if resp.status_code == 302:
            auth_cookies = session.cookies.get_dict()
            return {
                "status": "success",
                "message": "Login Verified!",
                "auth_data": auth_cookies
            }
        else:
            # اگر ڈائریکٹ verify.php فیل ہو تو signup.php پر ٹرائی کریں (Backup Logic)
            retry_url = f"https://jazzdrive.com.pk/oauth2/signup.php?id={data.session_id}"
            resp2 = session.post(retry_url, data={"otp": data.otp}, headers=HEADERS, allow_redirects=False)
            if resp2.status_code == 302:
                 return {"status": "success", "message": "Login Verified (Route 2)", "auth_data": session.cookies.get_dict()}
            
            return {"status": "fail", "message": "Invalid OTP", "resp_code": resp.status_code}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    # ٹائم آؤٹ بڑھا دیا ہے
    uvicorn.run(app, host="0.0.0.0", port=port, timeout_keep_alive=60)
