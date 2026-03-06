from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Path,
    Request,
    Response,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from scalar_fastapi import get_scalar_api_reference

from app.celery_app import celery_app
from app.config import (
    ALLOW_BROWSER_ACCESS,
    CORS_ALLOWED_ORIGINS,
    DOWNLOAD_ACCESS_HEADER_NAME,
)
from app.logger import get_logger
from app.middleware import SecurityMiddleware
from app.redis_client import redis_client
from app.schemas.api_docs import (
    ApiReadyResponse,
    DownloadRequest,
    DownloadStartedResponse,
    ErrorResponse,
    TaskStatusResponse,
)
from app.schemas.result import Result
from app.tasks import download_media_task
import os

# Configure logging
logger = get_logger(__name__)

# Determine environment
is_production = os.getenv("ENV", "development").lower() == "production"

API_TAGS = [
    {"name": "System", "description": "Service health and platform-level endpoints."},
    {"name": "Downloads", "description": "Start and monitor asynchronous download tasks."},
    {"name": "Files", "description": "Serve completed media files."},
]

SECURITY_RESPONSES = {
    401: {
        "model": ErrorResponse,
        "description": "Missing or invalid X-Firebase-AppCheck token when App Check is enabled.",
    },
    403: {
        "model": ErrorResponse,
        "description": (
            "Browser-like clients are blocked when ALLOW_BROWSER_ACCESS=false, "
            "or download access header is missing/invalid."
        ),
    },
    429: {
        "model": ErrorResponse,
        "description": "Rate limit exceeded, temporary ban active, or spam protection triggered.",
    },
    503: {
        "model": ErrorResponse,
        "description": "App Check is required by configuration but Firebase Admin is unavailable.",
    },
}

app = FastAPI(
    title="Media Downloader API",
    description=(
        "Download and serve media from supported platforms with asynchronous processing.\n\n"
        "Security headers:\n"
        f"- `{DOWNLOAD_ACCESS_HEADER_NAME}`: Required for all download-related endpoints.\n"
        "- `X-App-Secret`: Optional VIP bypass key for trusted clients.\n"
        "- `X-Firebase-AppCheck`: Required for non-VIP requests when `REQUIRE_FIREBASE_APPCHECK=true`."
    ),
    version="1.0.0",
    # Disable default docs in production (Scalar will be used instead)
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
    openapi_tags=API_TAGS,
)

if ALLOW_BROWSER_ACCESS:
    allow_any_origin = "*" in CORS_ALLOWED_ORIGINS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if allow_any_origin else CORS_ALLOWED_ORIGINS,
        allow_credentials=not allow_any_origin,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def security_header_docs(
    x_download_access: str | None = Header(
        default=None,
        alias=DOWNLOAD_ACCESS_HEADER_NAME,
        description="Required shared secret for download-related endpoints.",
    ),
    x_app_secret: str | None = Header(
        default=None,
        alias="X-App-Secret",
        description="VIP bypass secret. If valid, App Check and limits are bypassed.",
    ),
    x_firebase_appcheck: str | None = Header(
        default=None,
        alias="X-Firebase-AppCheck",
        description=(
            "Firebase App Check token. Required for non-VIP requests only when "
            "REQUIRE_FIREBASE_APPCHECK=true."
        ),
    ),
) -> None:
    # Header validation is enforced by middleware; this dependency exists for OpenAPI docs.
    _ = (x_download_access, x_app_secret, x_firebase_appcheck)


@app.middleware("http")
async def block_browser_clients(request: Request, call_next):
    if ALLOW_BROWSER_ACCESS:
        return await call_next(request)

    # Block CORS preflight outright
    if request.method == "OPTIONS":
        return JSONResponse(
            status_code=403,
            content=Result.fail("FORBIDDEN", 403)
            .with_message("Browser access is not allowed")
            .dict(),
        )

    # Block requests that look like browser JS
    origin = request.headers.get("origin")
    sec_fetch_site = request.headers.get("sec-fetch-site")

    if origin or sec_fetch_site:
        return JSONResponse(
            status_code=403,
            content=Result.fail("FORBIDDEN", 403)
            .with_message("Browser access is not allowed")
            .dict(),
        )

    return await call_next(request)


# Add Scalar API Reference (modern documentation UI)
@app.get("/scalar", include_in_schema=False)
async def scalar_docs():
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )


# Add Security Middleware
app.add_middleware(SecurityMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}", exc_info=True)

    env = os.getenv("ENV", "development").lower()
    error_message = str(exc) if env != "production" else "An unexpected error occurred."

    return JSONResponse(
        status_code=500,
        content=Result.fail("INTERNAL_ERROR", 500).with_message(error_message).dict(),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=Result.fail("HTTP_ERROR", exc.status_code).with_message(exc.detail).dict(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Don't expose internal pydantic errors in production
    if is_production:
        return JSONResponse(
            status_code=422,
            content=Result.fail("VALIDATION_ERROR", 422)
            .with_message("Invalid request parameters.")
            .dict(),
        )

    return JSONResponse(
        status_code=422,
        content=Result.fail("VALIDATION_ERROR", 422)
        .with_message("Validation error")
        .with_data({"errors": exc.errors()})  # Only safe in dev
        .dict(),
    )


@app.get(
    "/",
    tags=["System"],
    summary="Health check",
    response_model=ApiReadyResponse,
    responses=SECURITY_RESPONSES,
    dependencies=[Depends(security_header_docs)],
)
async def root():
    return Result.ok("API_READY").with_message("Media Downloader API is running.")


@app.post(
    "/download",
    tags=["Downloads"],
    summary="Start an asynchronous media download",
    response_model=DownloadStartedResponse,
    status_code=202,
    responses={
        **SECURITY_RESPONSES,
        400: {
            "model": ErrorResponse,
            "description": "Invalid URL, unsupported platform, or pre-flight metadata failure.",
        },
        413: {
            "model": ErrorResponse,
            "description": "Estimated media size exceeds allowed limit.",
        },
    },
    dependencies=[Depends(security_header_docs)],
)
async def start_download(payload: DownloadRequest, request: Request):
    url = (payload.url or "").strip()
    if not url:
        return JSONResponse(
            status_code=400,
            content=Result.fail("INVALID_URL", 400).with_message("URL is required.").dict(),
        )

    # Get client IP for volume tracking (Prefer Cloudflare Header)
    client_ip = request.headers.get("CF-Connecting-IP") or request.headers.get(
        "X-Real-IP"
    ) or request.headers.get("X-Forwarded-For", request.client.host
    ).split(",")[
        0
    ]

    # Validate that URL is from a supported platform
    from app.utils import clean_youtube_url, validate_supported_platform

    try:
        platform = validate_supported_platform(url)
        if platform == "youtube":
            url = clean_youtube_url(url)
            logger.info(f"Cleaned YouTube URL: {url}")
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content=Result.fail("UNSUPPORTED_PLATFORM", 400).with_message(str(exc)).dict(),
        )

    # --- PRE-FLIGHT SIZE CHECK ---
    # Check file size BEFORE queueing the download task
    from app.downloader import Downloader

    try:
        downloader = Downloader()
        info = downloader.get_info(url, cookie_profile=payload.cookie_profile)

        # Get estimated file size using improved multi-method estimation
        size_mb, estimation_method = downloader.estimate_file_size_mb(info)
        logger.info(f"Pre-flight size estimate: {size_mb:.1f}MB (method: {estimation_method})")

        # Import limits from config
        from app.config import MAX_FILE_SIZE_MB, MAX_HOURLY_VOLUME_MB

        is_vip = getattr(request.state, "is_vip", False)
        if is_vip:
            logger.info(f"VIP Request detected (IP={client_ip}). Skipping limits.")

        # Check 1: Single file size limit
        if not is_vip and size_mb > MAX_FILE_SIZE_MB:
            return JSONResponse(
                status_code=413,
                content=Result.fail("FILE_TOO_LARGE", 413)
                .with_message(f"File size ({size_mb:.1f}MB) exceeds limit ({MAX_FILE_SIZE_MB}MB)")
                .dict(),
            )

        # Check 2: Hourly volume limit - would this file exceed remaining quota?
        if not is_vip and redis_client.is_available():
            volume_key = f"volume_mb:{client_ip}"
            current_volume = redis_client.client.get(volume_key)
            current_volume_mb = float(current_volume) if current_volume else 0.0

            # If size is known, check if it would exceed quota
            if size_mb > 0:
                projected_volume = current_volume_mb + size_mb
                if projected_volume > MAX_HOURLY_VOLUME_MB:
                    return JSONResponse(
                        status_code=429,
                        content=Result.fail("VOLUME_LIMIT_EXCEEDED", 429)
                        .with_message(
                            f"This download ({size_mb:.1f}MB) would exceed hourly limit. "
                            f"Current: {current_volume_mb:.1f}MB, Limit: {MAX_HOURLY_VOLUME_MB}MB"
                        )
                        .dict(),
                    )
            else:
                # Size unknown - check if we have remaining quota (at least 50MB buffer)
                if current_volume_mb >= (MAX_HOURLY_VOLUME_MB - MAX_FILE_SIZE_MB):
                    return JSONResponse(
                        status_code=429,
                        content=Result.fail("VOLUME_LIMIT_EXCEEDED", 429)
                        .with_message(
                            f"Cannot determine file size and quota is low "
                            f"({current_volume_mb:.1f}MB/{MAX_HOURLY_VOLUME_MB}MB)"
                        )
                        .dict(),
                    )

        logger.info(f"Pre-flight check passed: {url} - estimated size: {size_mb:.1f}MB")

    except Exception as exc:
        logger.error(f"Pre-flight check failed for {url}: {exc}")
        # Production-safe error message
        error_message = "Medya bilgisi alınamadı. Lütfen URL'yi kontrol edip tekrar deneyin."
        return JSONResponse(
            status_code=400,
            content=Result.fail("PREFLIGHT_FAILED", 400).with_message(error_message).dict(),
        )

    # Trigger Celery Task with client IP for volume tracking
    # Use apply_async to set dynamic timeouts (1 hour for VIP, 10 mins for regular)
    time_limit = 3600 if is_vip else 600
    task = download_media_task.apply_async(
        args=[url, client_ip, is_vip, payload.cookie_profile],
        time_limit=time_limit,
        soft_time_limit=time_limit - 60,  # 1 minute cleanup buffer
    )

    # Store task mapping in Redis for idempotency (matching hash in middleware)
    import hashlib

    hash_input = f"{url}|{payload.cookie_profile or ''}"
    url_hash = hashlib.sha256(hash_input.encode()).hexdigest()
    if redis_client.is_available():
        redis_client.client.set(f"download_status:{url_hash}", task.id, ex=3600)

    return JSONResponse(
        status_code=202,
        content=Result.ok("DOWNLOAD_STARTED", 202)
        .with_data(
            {
                "task_id": task.id,
                "estimated_size_mb": round(size_mb, 1) if size_mb > 0 else None,
            }
        )
        .dict(),
    )


@app.get(
    "/status/{task_id}",
    tags=["Downloads"],
    summary="Get asynchronous task status",
    response_model=TaskStatusResponse,
    responses=SECURITY_RESPONSES,
    dependencies=[Depends(security_header_docs)],
)
async def get_status(
    task_id: str = Path(..., description="Task ID returned by /download."),
):
    task_result = celery_app.AsyncResult(task_id)

    response_data = {
        "task_id": task_id,
        "status": task_result.status,
    }

    if task_result.status == "SUCCESS":
        response_data.update(task_result.result)
        return Result.ok("TASK_COMPLETED").with_data(response_data)
    if task_result.status == "REVOKED":
        return Result.fail("TASK_CANCELLED", 200).with_data(response_data).with_message(
            "Task cancelled."
        )
    if task_result.status == "FAILURE":
        # Log the actual error but return a safe message to the user
        logger.error(f"Task {task_id} failed: {task_result.info}")
        return Result.fail("TASK_FAILED", 500).with_message(
            "İndirme işlemi başarısız oldu. Lütfen daha sonra tekrar deneyin."
        )

    # PENDING or PROGRESS
    info = (
        task_result.info
        if isinstance(task_result.info, dict)
        else {"status": str(task_result.info)}
    )
    response_data.update(info)
    return Result.ok("TASK_IN_PROGRESS").with_data(response_data)


@app.post(
    "/status/{task_id}/cancel",
    tags=["Downloads"],
    summary="Cancel asynchronous task",
    responses=SECURITY_RESPONSES,
    dependencies=[Depends(security_header_docs)],
)
async def cancel_task(
    task_id: str = Path(..., description="Task ID returned by /download."),
):
    celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
    return Result.ok("TASK_CANCEL_REQUESTED").with_data({"task_id": task_id})


def cleanup_file(path: str):
    """Instant cleanup: delete file after delivery."""
    try:
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"Instantly cleaned up file: {path}")
    except Exception as exc:
        logger.error(f"Error during cleanup of {path}: {exc}")


@app.get(
    "/files/{task_id}",
    tags=["Files"],
    summary="Download completed media file",
    responses={
        **SECURITY_RESPONSES,
        200: {
            "description": "Binary file stream (served via X-Accel-Redirect).",
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
            "headers": {
                "Content-Disposition": {
                    "description": "Attachment header with UTF-8 encoded filename.",
                    "schema": {"type": "string"},
                },
                "Content-Type": {
                    "description": "Detected MIME type of the downloaded file.",
                    "schema": {"type": "string"},
                },
            },
        },
        404: {
            "model": ErrorResponse,
            "description": "Task not completed yet or output file missing.",
        },
        500: {
            "model": ErrorResponse,
            "description": "Unexpected file lookup or server error.",
        },
    },
    dependencies=[Depends(security_header_docs)],
)
async def get_file(
    background_tasks: BackgroundTasks,
    task_id: str = Path(..., description="Task ID returned by /download."),
):
    task_result = celery_app.AsyncResult(task_id)
    if not task_result.ready() or task_result.status != "SUCCESS":
        return JSONResponse(
            status_code=404,
            content=Result.fail("FILE_NOT_READY", 404)
            .with_message("File not ready or task failed.")
            .dict(),
        )

    # task_result.result is a dict like {'success': True, 'data': {...}}
    result_dict = task_result.result
    # Handle case where result might be just the data (legacy) or wrapped in Result
    file_info = (
        result_dict.get("data") if isinstance(result_dict, dict) and "data" in result_dict else result_dict
    )

    if not file_info:
        logger.error(f"Task result has no data: {result_dict}")
        return JSONResponse(
            status_code=500,
            content=Result.fail("INVALID_TASK_RESULT", 500)
            .with_message("Task result format invalid.")
            .dict(),
        )

    file_path = file_info.get("file_path")
    filename = file_info.get("filename")

    if not file_path or not os.path.exists(file_path):
        logger.error(f"File lookup failed. Path: {file_path}, CWD: {os.getcwd()}")
        try:
            dir_content = os.listdir("downloads")
            logger.error(f"Downloads dir content: {dir_content}")

            # Attempt to find the file if it's just a path issue
            # Check if basename exists in downloads/
            if file_path:
                target_name = os.path.basename(file_path)
            elif filename:
                target_name = filename
            else:
                target_name = "unknown"

            if target_name in dir_content:
                # Fix path
                file_path = os.path.join("downloads", target_name)
                logger.info(f"Fixed path to: {file_path}")
            else:
                # Only return available_files if NOT in production
                debug_data = {}
                if not is_production:
                    debug_data["available_files"] = dir_content

                return JSONResponse(
                    status_code=404,
                    content=Result.fail("FILE_NOT_FOUND", 404)
                    .with_message(f"File not found. Searched for: {target_name}")
                    .with_data(debug_data)
                    .dict(),
                )
        except Exception as exc:
            logger.error(f"Could not list downloads dir: {exc}")
            return JSONResponse(
                status_code=500,
                content=Result.fail("INTERNAL_ERROR", 500)
                .with_message("Dosya aranırken bir hata oluştu.")
                .dict(),
            )

    # 1. OPTIMAL: Use X-Accel-Redirect for Nginx to serve the file
    # The path must start with the 'internal' location defined in nginx.conf
    # We must URL-encode the filename for Nginx and headers to handle special characters
    from urllib.parse import quote

    # Nginx expects URL-encoded path for X-Accel-Redirect
    # E.g. "my file.mp4" -> "my%20file.mp4"
    encoded_filename = quote(filename)

    response = Response()
    response.headers["X-Accel-Redirect"] = f"/_internal_downloads/{encoded_filename}"

    # RFC 5987: filename*=UTF-8''encoded_filename
    # This ensures browsers handle non-ASCII filenames correctly
    response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_filename}"

    # 3. Dynamic Content-Type using mimetypes
    import mimetypes

    content_type, _ = mimetypes.guess_type(filename)
    if not content_type:
        content_type = "application/octet-stream"

    response.headers["Content-Type"] = content_type

    # 2. Cleanup Strategy
    background_tasks.add_task(delayed_cleanup, file_path, delay=60)

    return response


async def delayed_cleanup(path: str, delay: int):
    """Wait and then cleanup to ensure Nginx finished serving."""
    import asyncio

    await asyncio.sleep(delay)
    cleanup_file(path)
