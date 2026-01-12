import time
import hashlib
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.redis_client import redis_client
from app.schemas.result import Result
from fastapi.responses import JSONResponse
import firebase_admin
from firebase_admin import app_check, credentials
import os
import logging

logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK
firebase_cert_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
if firebase_cert_path and os.path.exists(firebase_cert_path):
    cred = credentials.Certificate(firebase_cert_path)
    firebase_admin.initialize_app(cred)
else:
    logger.warning("Firebase Service Account JSON not found. App Check will be bypassed in dev mode.")

class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Get Client IP
        client_ip = request.headers.get("X-Forwarded-For", request.client.host).split(",")[0]
        
        # 2. Bypass for Testing/Dev (X-App-Secret)
        is_dev = os.getenv("ENV", "development").lower() != "production"
        app_secret = os.getenv("APP_SECRET_KEY", "dev_secret_bypass")
        request_secret = request.headers.get("X-App-Secret")
        
        can_bypass = is_dev and request_secret == app_secret
        
        # 3. Check if IP is banned
        if redis_client.is_available() and not can_bypass:
            if redis_client.client.exists(f"ban:{client_ip}"):
                return self._fail_response("TOO_MANY_REQUESTS", 429, "You are temporarily banned due to spamming.")

        # 4. Firebase App Check (Professional Grade)
        if firebase_cert_path and not can_bypass:
            app_check_token = request.headers.get("X-Firebase-AppCheck")
            if not app_check_token:
                return self._fail_response("INVALID_TOKEN", 401, "Missing App Check token.")
            try:
                app_check.verify_token(app_check_token)
            except Exception as e:
                logger.error(f"App Check verification failed: {e}")
                return self._fail_response("INVALID_TOKEN", 401, "Invalid App Check token.")

        # 5. Rate Limiting (30/hr)
        if redis_client.is_available() and not can_bypass:
            rate_limit_key = f"rate_limit:{client_ip}"
            current_hits = redis_client.client.incr(rate_limit_key)
            if current_hits == 1:
                redis_client.client.expire(rate_limit_key, 3600)
            
            if current_hits > 30:
                return self._fail_response("TOO_MANY_REQUESTS", 429, "Rate limit exceeded (30/hr).")

        # 6. Idempotency & Spam Detection
        if request.method == "POST" and "/download" in request.url.path and not can_bypass:
            body = await request.json()
            url = body.get("url", "")
            if url:
                url_hash = hashlib.sha256(url.encode()).hexdigest()
                idempotency_key = f"download_status:{url_hash}"
                
                # Check if already processing
                if redis_client.is_available() and redis_client.client.exists(idempotency_key):
                    # Spam protection: increment hits for same URL
                    spam_hits_key = f"idempotency_hits:{client_ip}"
                    hits = redis_client.client.incr(spam_hits_key)
                    if hits == 1:
                        redis_client.client.expire(spam_hits_key, 60)
                    
                    if hits >= 5:
                        redis_client.client.set(f"ban:{client_ip}", "true", ex=300) # 5 min ban
                        return self._fail_response("SPAM_DETECTED", 429, "Spam detected. You are banned for 5 minutes.")
                    
                    return self._fail_response("DOWNLOAD_ALREADY_IN_PROGRESS", 202, "This URL is already being processed.")

        response = await call_next(request)
        return response

    def _fail_response(self, code: str, status_code: int, message: str):
        return JSONResponse(
            status_code=status_code,
            content=Result.fail(code, status_code).with_message(message).dict()
        )
