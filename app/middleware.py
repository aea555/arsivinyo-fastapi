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
from app.logger import get_logger

logger = get_logger(__name__)

# Initialize Firebase Admin SDK (Only if not in dev bypass mode or if config is explicitly provided)
is_prod = os.getenv("ENV", "development").lower() == "production"
firebase_cert_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
firebase_initialized = False

if firebase_cert_path and os.path.exists(firebase_cert_path):
    try:
        cred = credentials.Certificate(firebase_cert_path)
        firebase_admin.initialize_app(cred)
        firebase_initialized = True
        logger.info("Firebase Admin SDK initialized successfully.")
    except Exception as e:
        logger.error(f"Firebase initialization failed: {e}. App Check will be bypassed if enabled.")
elif is_prod:
    logger.warning("FIREBASE_SERVICE_ACCOUNT_JSON not found in PRODUCTION! App Check will fail.")

class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 0. Allow OPTIONS (CORS Preflight) - Critical for Production
        if request.method == "OPTIONS":
            return await call_next(request)

        # 1. Get Client IP (Prefer Cloudflare Header)
        client_ip = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For", request.client.host).split(",")[0]
        
        # 2. VIP / Developer Bypass (X-App-Secret)
        # Allows trusted apps (e.g. invalid-free family version) to bypass App Check AND Rate Limits
        app_secret = os.getenv("APP_SECRET_KEY") # Must be set in .env!
        request_secret = request.headers.get("X-App-Secret")
        
        # Security Note: If APP_SECRET_KEY is not set in env, deny bypass by default for safety
        can_bypass = (app_secret is not None) and (request_secret == app_secret)
        
        # Store VIP status for endpoints (to skip volume limits etc.)
        request.state.is_vip = can_bypass
        
        # DEBUG: Log bypass status
        if request.url.path == "/download":
            logger.debug(f"IP={client_ip}, can_bypass={can_bypass}")
        
        # 3. Check if IP is banned
        if redis_client.is_available() and not can_bypass:
            if redis_client.client.exists(f"ban:{client_ip}"):
                logger.warning(f"[429 BANNED] IP={client_ip}")
                return self._fail_response("TOO_MANY_REQUESTS", 429, "You are temporarily banned due to spamming.")

        # 4. Firebase App Check (Professional Grade)
        if firebase_initialized and not can_bypass:
            app_check_token = request.headers.get("X-Firebase-AppCheck")
            if not app_check_token:
                return self._fail_response("INVALID_TOKEN", 401, "Missing App Check token.")
            try:
                app_check.verify_token(app_check_token)
            except Exception as e:
                logger.error(f"App Check verification failed: {e}")
                return self._fail_response("INVALID_TOKEN", 401, "Invalid App Check token.")

        # 5. Rate Limiting (per hour)
        if redis_client.is_available() and not can_bypass:
            from app.config import RATE_LIMIT_REQUESTS_PER_HOUR
            rate_limit_key = f"rate_limit:{client_ip}"
            current_hits = redis_client.client.incr(rate_limit_key)
            if current_hits == 1:
                redis_client.client.expire(rate_limit_key, 3600)
            
            if current_hits > RATE_LIMIT_REQUESTS_PER_HOUR:
                logger.warning(f"[429 RATE_LIMIT] IP={client_ip}, hits={current_hits}")
                return self._fail_response("TOO_MANY_REQUESTS", 429, f"Rate limit exceeded ({RATE_LIMIT_REQUESTS_PER_HOUR}/hr).")


        # (Volume limit check moved to API endpoint for pre-flight verification)


        # 6. Idempotency & Spam Detection
        if request.method == "POST" and "/download" in request.url.path and not can_bypass:
            # Cache the body so it can be read again by the endpoint
            body_bytes = await request.body()
            try:
                import json
                body = json.loads(body_bytes)
            except json.JSONDecodeError:
                body = {}
                
            url = body.get("url", "")
            if url:
                url_hash = hashlib.sha256(url.encode()).hexdigest()
                idempotency_key = f"download_status:{url_hash}"
                
                # Check if already processing
                if redis_client.is_available() and redis_client.client.exists(idempotency_key):
                    # Get the existing task ID and check its status
                    existing_task_id = redis_client.client.get(idempotency_key)
                    if existing_task_id:
                        existing_task_id = existing_task_id.decode() if isinstance(existing_task_id, bytes) else existing_task_id
                        from app.celery_app import celery_app
                        task_result = celery_app.AsyncResult(existing_task_id)
                        
                        # Only block if task is STILL in progress
                        if task_result.status in ['PENDING', 'STARTED', 'PROGRESS', 'RETRY']:
                            # Spam protection: increment hits for same URL
                            spam_hits_key = f"idempotency_hits:{client_ip}"
                            hits = redis_client.client.incr(spam_hits_key)
                            if hits == 1:
                                redis_client.client.expire(spam_hits_key, 60)
                            
                            if hits >= 5:
                                logger.warning(f"[429 SPAM_BAN] IP={client_ip}, hits={hits}")
                                redis_client.client.set(f"ban:{client_ip}", "true", ex=300) # 5 min ban
                                return self._fail_response("SPAM_DETECTED", 429, "Spam detected. You are banned for 5 minutes.")
                            
                            logger.info(f"[202 IDEMPOTENCY] IP={client_ip}, URL already processing (task={existing_task_id})")
                            return self._fail_response("DOWNLOAD_ALREADY_IN_PROGRESS", 202, "This URL is already being processed.")
                        else:
                            # Task completed (SUCCESS/FAILURE), allow new download
                            logger.info(f"Previous task {existing_task_id} completed ({task_result.status}), allowing new download")
            
            # Restore body for the endpoint by creating a new receive callable
            async def receive():
                return {"type": "http.request", "body": body_bytes}
            request._receive = receive

        response = await call_next(request)
        return response

    def _fail_response(self, code: str, status_code: int, message: str):
        return JSONResponse(
            status_code=status_code,
            content=Result.fail(code, status_code).with_message(message).dict()
        )
