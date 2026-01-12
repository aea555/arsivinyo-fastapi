from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Response
from fastapi.responses import JSONResponse, FileResponse
from app.schemas.result import Result
from app.middleware import SecurityMiddleware
from app.tasks import download_media_task
from app.celery_app import celery_app
from app.redis_client import redis_client
import logging
import os
import shutil

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Media Downloader API",
    description="API for downloading media from various platforms with metadata manipulation.",
    version="1.0.0"
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
        content=Result.fail("INTERNAL_ERROR", 500)
        .with_message(error_message)
        .dict()
    )

@app.get("/")
async def root():
    return Result.ok("API_READY").with_message("Media Downloader API is running.")

@app.post("/download")
async def start_download(request: Request):
    body = await request.json()
    url = body.get("url")
    if not url:
        return JSONResponse(
            status_code=400,
            content=Result.fail("INVALID_URL", 400).with_message("URL is required.").dict()
        )
    
    # Trigger Celery Task
    task = download_media_task.delay(url)
    
    # Store task mapping in Redis for idempotency (matching hash in middleware)
    import hashlib
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    if redis_client.is_available():
        redis_client.client.set(f"download_status:{url_hash}", task.id, ex=3600)

    return Result.ok("DOWNLOAD_STARTED", 202).with_data({"task_id": task.id})

@app.get("/status/{task_id}")
async def get_status(task_id: str):
    task_result = celery_app.AsyncResult(task_id)
    
    response_data = {
        "task_id": task_id,
        "status": task_result.status,
    }
    
    if task_result.status == 'SUCCESS':
        response_data.update(task_result.result)
        return Result.ok("TASK_COMPLETED").with_data(response_data)
    elif task_result.status == 'FAILURE':
        return Result.fail("TASK_FAILED", 500).with_data({"error": str(task_result.info)})
    else:
        # PENDING or PROGRESS
        info = task_result.info if isinstance(task_result.info, dict) else {"status": str(task_result.info)}
        response_data.update(info)
        return Result.ok("TASK_IN_PROGRESS").with_data(response_data)

def cleanup_file(path: str):
    """Instant cleanup: delete file after delivery."""
    try:
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"Instantly cleaned up file: {path}")
    except Exception as e:
        logger.error(f"Error during cleanup of {path}: {e}")

@app.get("/files/{task_id}")
async def get_file(task_id: str, background_tasks: BackgroundTasks):
    task_result = celery_app.AsyncResult(task_id)
    if not task_result.ready() or task_result.status != 'SUCCESS':
        return JSONResponse(
            status_code=404,
            content=Result.fail("FILE_NOT_READY", 404).with_message("File not ready or task failed.").dict()
        )
    
    file_info = task_result.result
    file_path = file_info.get("file_path")
    filename = file_info.get("filename")
    
    if not file_path or not os.path.exists(file_path):
        return JSONResponse(
            status_code=404,
            content=Result.fail("FILE_NOT_FOUND", 404).with_message("File not found on server.").dict()
        )
    
    # 1. OPTIMAL: Use X-Accel-Redirect for Nginx to serve the file
    # This offloads the file transfer to Nginx (high performance)
    # The path must start with the 'internal' location defined in nginx.conf
    response = Response()
    response.headers["X-Accel-Redirect"] = f"/_internal_downloads/{filename}"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Content-Type"] = "application/octet-stream"

    # 2. Cleanup Strategy: In the context of X-Accel-Redirect, 
    # we can't delete immediately because Nginx needs the file.
    # We will schedule a cleanup task for 1 minute later.
    background_tasks.add_task(delayed_cleanup, file_path, delay=60)
    
    return response

async def delayed_cleanup(path: str, delay: int):
    """Wait and then cleanup to ensure Nginx finished serving."""
    import asyncio
    await asyncio.sleep(delay)
    cleanup_file(path)
