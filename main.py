import os
import uvicorn
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from playwright.sync_api import sync_playwright

app = FastAPI()

# --- ڈیٹا ماڈلز (Data Models) ---
class LoginRequest(BaseModel):
    phone: str

class VerifyRequest(BaseModel):
    otp: str
    session_id: str

# --- ہیڈرز ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://jazzdrive.com.pk",
    "Referer": "https://jazzdrive.com.pk"
}

# --- 1. ID نکالنے اور OTP بھیجنے کا فنکشن ---
@app.post("/send-otp")
def send_otp(data: LoginRequest):
    session_id = None
    print("Launching Browser to get ID...")

    try:
        # Playwright براؤزر لانچ کریں
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=HEADERS["User-Agent"])
            page = context.new_page()

            # کلاؤڈ لنک کھولیں
            page.goto("https://cloud.jazzdrive.com.pk")
            
            # ری-ڈائریکٹ کا انتظار کریں (زیادہ سے زیادہ 30 سیکنڈ)
            try:
                page.wait_for_url("**/verify.php?id=*", timeout=30000)
                final_url = page.url
                
                if "id=" in final_url:
                    # URL سے ID الگ کریں
                    session_id = final_url.split("id=")[1].split("&")[0]
            except Exception as e:
                print(f"Timeout or Error: {e}")
            finally:
                browser.close()

        if not session_id:
            raise HTTPException(status_code=500, detail="Failed to retrieve Session ID from Cloud.")

        # اب API کے ذریعے نمبر بھیجیں
        api_url = f"https://jazzdrive.com.pk/oauth2/signup.php?id={session_id}"
        payload = {"msisdn": data.phone, "enrichment_status": ""}
        
        resp = requests.post(api_url, data=payload, headers=HEADERS)
        
        if resp.status_code in [200, 302]:
            return {
                "status": "success",
                "message": "OTP Sent",
                "session_id": session_id  # یہ ID سنبھال کر رکھیں، اگلے سٹیپ میں چاہیے
            }
        else:
            return {"status": "fail", "message": "Could not send OTP", "debug": resp.text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- 2. OTP ویریفائی کرنے کا فنکشن ---
@app.post("/verify-otp")
def verify_otp(data: VerifyRequest):
    verify_url = f"https://jazzdrive.com.pk/verify.php?id={data.session_id}"
    payload = {"otp": data.otp}
    
    session = requests.Session()
    try:
        # OTP بھیجیں (Redirects کو روک کر رکھیں تاکہ کوکیز پکڑ سکیں)
        resp = session.post(verify_url, data=payload, headers=HEADERS, allow_redirects=False)
        
        if resp.status_code == 302:
            # لاگ ان کامیاب! کوکیز حاصل کریں
            auth_cookies = session.cookies.get_dict()
            return {
                "status": "success",
                "message": "Login Verified!",
                "auth_data": auth_cookies
            }
        else:
            return {"status": "fail", "message": "Invalid OTP or Session Expired"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- ریلوے (Railway) کے لیے سٹارٹ کمانڈ ---
if __name__ == "__main__":
    # ریلوے کا PORT اٹھائیں، ورنہ 8000 استعمال کریں
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
