import hashlib
import hmac
import os

import firebase_admin
from fastapi import Request
from fastapi.responses import JSONResponse
from firebase_admin import app_check, credentials
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import RATE_LIMIT_REQUESTS_PER_HOUR
from app.config import (
    APP_SECRET_KEY,
    DOWNLOAD_ACCESS_HEADER_NAME,
    DOWNLOAD_ACCESS_KEY,
    FIREBASE_SERVICE_ACCOUNT_JSON,
    REQUIRE_DOWNLOAD_ACCESS_HEADER,
    REQUIRE_FIREBASE_APPCHECK,
)
from app.logger import get_logger
from app.redis_client import redis_client
from app.schemas.result import Result

logger = get_logger(__name__)

firebase_initialized = False

if FIREBASE_SERVICE_ACCOUNT_JSON and os.path.exists(FIREBASE_SERVICE_ACCOUNT_JSON):
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_JSON)
            firebase_admin.initialize_app(cred)
        firebase_initialized = True
        logger.info("Firebase Admin SDK initialized successfully.")
    except Exception as exc:
        logger.error(f"Firebase initialization failed: {exc}")
elif REQUIRE_FIREBASE_APPCHECK:
    logger.warning(
        "REQUIRE_FIREBASE_APPCHECK=true but FIREBASE_SERVICE_ACCOUNT_JSON is missing or invalid. "
        "Non-VIP requests will be rejected."
    )


def _normalize_header(value: str | None) -> str:
    return value.strip() if isinstance(value, str) else ""


def _is_download_protected_path(path: str) -> bool:
    return (
        path == "/download"
        or path.startswith("/status/")
        or path.startswith("/files/")
    )


def _is_vip_request(request: Request) -> bool:
    # If APP_SECRET_KEY is not set, bypass is disabled by default for safety.
    if not APP_SECRET_KEY:
        return False

    request_secret = _normalize_header(request.headers.get("X-App-Secret"))
    expected_secret = APP_SECRET_KEY.strip()

    if not request_secret or not expected_secret:
        return False

    return hmac.compare_digest(request_secret, expected_secret)


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 0. Allow OPTIONS (CORS Preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # 1. Get Client IP (Prefer Cloudflare Header)
        client_ip = request.headers.get("CF-Connecting-IP") or request.headers.get(
            "X-Real-IP"
        ) or request.headers.get("X-Forwarded-For", request.client.host).split(",")[
            0
        ]

        # 2. Download access gate (required for download-related endpoints)
        if REQUIRE_DOWNLOAD_ACCESS_HEADER and _is_download_protected_path(request.url.path):
            expected_access_key = (DOWNLOAD_ACCESS_KEY or "").strip()
            if not expected_access_key:
                logger.error(
                    "REQUIRE_DOWNLOAD_ACCESS_HEADER=true but DOWNLOAD_ACCESS_KEY is missing."
                )
                return self._fail_response(
                    "SERVICE_UNAVAILABLE",
                    503,
                    "Download access is not configured on the server.",
                )

            request_access_key = _normalize_header(
                request.headers.get(DOWNLOAD_ACCESS_HEADER_NAME)
            )
            if not request_access_key or not hmac.compare_digest(
                request_access_key, expected_access_key
            ):
                logger.warning(
                    f"[403 DOWNLOAD_ACCESS] IP={client_ip}, path={request.url.path}"
                )
                return self._fail_response(
                    "FORBIDDEN",
                    403,
                    f"Missing or invalid {DOWNLOAD_ACCESS_HEADER_NAME} header.",
                )

        # 3. VIP / Developer Bypass (X-App-Secret)
        can_bypass = _is_vip_request(request)

        # Store VIP status for endpoints (to skip volume limits etc.)
        request.state.is_vip = can_bypass

        # DEBUG: Log bypass status
        if request.url.path == "/download":
            logger.debug(f"IP={client_ip}, can_bypass={can_bypass}")

        # 4. Check if IP is banned
        if redis_client.is_available() and not can_bypass:
            if redis_client.client.exists(f"ban:{client_ip}"):
                logger.warning(f"[429 BANNED] IP={client_ip}")
                return self._fail_response(
                    "TOO_MANY_REQUESTS",
                    429,
                    "You are temporarily banned due to spamming.",
                )

        # 5. Firebase App Check (configurable)
        # VIP mode must bypass App Check completely.
        if REQUIRE_FIREBASE_APPCHECK and not can_bypass:
            if not firebase_initialized:
                logger.error("App Check is required but Firebase Admin SDK is not initialized.")
                return self._fail_response(
                    "SERVICE_UNAVAILABLE",
                    503,
                    "App Check is required but not configured on the server.",
                )

            app_check_token = _normalize_header(request.headers.get("X-Firebase-AppCheck"))
            if not app_check_token:
                return self._fail_response("INVALID_TOKEN", 401, "Missing App Check token.")
            try:
                app_check.verify_token(app_check_token)
            except Exception as exc:
                logger.error(f"App Check verification failed: {exc}")
                return self._fail_response("INVALID_TOKEN", 401, "Invalid App Check token.")

        # 6. Rate Limiting (per hour)
        if redis_client.is_available() and not can_bypass:
            rate_limit_key = f"rate_limit:{client_ip}"
            current_hits = redis_client.client.incr(rate_limit_key)
            if current_hits == 1:
                redis_client.client.expire(rate_limit_key, 3600)

            if current_hits > RATE_LIMIT_REQUESTS_PER_HOUR:
                logger.warning(f"[429 RATE_LIMIT] IP={client_ip}, hits={current_hits}")
                return self._fail_response(
                    "TOO_MANY_REQUESTS",
                    429,
                    f"Rate limit exceeded ({RATE_LIMIT_REQUESTS_PER_HOUR}/hr).",
                )

        # (Volume limit check moved to API endpoint for pre-flight verification)

        # 7. Idempotency & Spam Detection
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
                cookie_profile = body.get("cookie_profile", "")
                hash_input = f"{url}|{cookie_profile}"
                url_hash = hashlib.sha256(hash_input.encode()).hexdigest()
                idempotency_key = f"download_status:{url_hash}"

                # Check if already processing
                if redis_client.is_available() and redis_client.client.exists(idempotency_key):
                    # Get the existing task ID and check its status
                    existing_task_id = redis_client.client.get(idempotency_key)
                    if existing_task_id:
                        existing_task_id = (
                            existing_task_id.decode()
                            if isinstance(existing_task_id, bytes)
                            else existing_task_id
                        )
                        from app.celery_app import celery_app

                        task_result = celery_app.AsyncResult(existing_task_id)

                        # Only block if task is STILL in progress
                        if task_result.status in ["PENDING", "STARTED", "PROGRESS", "RETRY"]:
                            # Spam protection: increment hits for same URL
                            spam_hits_key = f"idempotency_hits:{client_ip}"
                            hits = redis_client.client.incr(spam_hits_key)
                            if hits == 1:
                                redis_client.client.expire(spam_hits_key, 60)

                            if hits >= 5:
                                logger.warning(f"[429 SPAM_BAN] IP={client_ip}, hits={hits}")
                                redis_client.client.set(
                                    f"ban:{client_ip}",
                                    "true",
                                    ex=300,
                                )  # 5 min ban
                                return self._fail_response(
                                    "SPAM_DETECTED",
                                    429,
                                    "Spam detected. You are banned for 5 minutes.",
                                )

                            logger.info(
                                f"[202 IDEMPOTENCY] IP={client_ip}, URL already processing (task={existing_task_id})"
                            )
                            return self._fail_response(
                                "DOWNLOAD_ALREADY_IN_PROGRESS",
                                202,
                                "This URL is already being processed.",
                            )
                        else:
                            # Task completed (SUCCESS/FAILURE), allow new download
                            logger.info(
                                f"Previous task {existing_task_id} completed ({task_result.status}), allowing new download"
                            )

            # Restore body for the endpoint by creating a new receive callable
            async def receive():
                return {"type": "http.request", "body": body_bytes}

            request._receive = receive

        response = await call_next(request)
        return response

    def _fail_response(self, code: str, status_code: int, message: str):
        return JSONResponse(
            status_code=status_code,
            content=Result.fail(code, status_code).with_message(message).dict(),
        )
