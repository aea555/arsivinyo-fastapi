from app.celery_app import celery_app
from app.downloader import Downloader
from app.metadata import update_creation_time
from app.schemas.result import Result
from app.redis_client import redis_client
from app.config import MAX_FILE_SIZE_MB
import os
from datetime import datetime
from app.logger import get_logger

logger = get_logger(__name__)


def track_volume(client_ip: str, file_size_mb: float):
    """Track downloaded volume in Redis for hourly limit enforcement."""
    if not redis_client.is_available():
        return
    
    volume_key = f"volume_mb:{client_ip}"
    current_volume = redis_client.client.get(volume_key)
    current_volume_mb = float(current_volume) if current_volume else 0.0
    new_volume = current_volume_mb + file_size_mb
    
    # Set with 1 hour expiry
    redis_client.client.set(volume_key, str(new_volume), ex=3600)
    logger.info(f"Volume tracked for {client_ip}: {file_size_mb:.2f}MB (total: {new_volume:.2f}MB)")

@celery_app.task(bind=True, name="app.tasks.download_media")
def download_media_task(self, url: str, client_ip: str = "unknown"):
    """Celery task to download media and update metadata."""
    downloader = Downloader()
    
    try:
        # 1. Extract info FIRST to check file size
        self.update_state(state='PROGRESS', meta={'status': 'Checking file size...'})
        info = downloader.get_info(url)
        
        # 2. Enforce file size limit BEFORE downloading
        if not downloader.check_file_size(info, limit_mb=MAX_FILE_SIZE_MB):
            filesize = info.get('filesize') or info.get('filesize_approx') or 0
            size_mb = filesize / (1024 * 1024) if filesize else 0
            error_msg = f"File size ({size_mb:.1f}MB) exceeds limit ({MAX_FILE_SIZE_MB}MB)"
            logger.warning(f"Rejecting download for {url}: {error_msg}")
            return Result.fail("FILE_TOO_LARGE", 413).with_message(error_msg).dict()
        
        # 3. Download the media (size is acceptable)
        self.update_state(state='PROGRESS', meta={'status': 'Downloading...'})
        file_path = downloader.download(url)
        
        # 4. Update metadata
        self.update_state(state='PROGRESS', meta={'status': 'Updating metadata...'})
        update_creation_time(file_path)
        
        # 5. Track volume for hourly limit
        actual_size_bytes = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        actual_size_mb = actual_size_bytes / (1024 * 1024)
        track_volume(client_ip, actual_size_mb)
        
        return Result.ok("DOWNLOAD_COMPLETED").with_data({
            "file_path": file_path,
            "filename": os.path.basename(file_path),
            "size_mb": round(actual_size_mb, 2)
        }).dict()
        
    except Exception as e:
        logger.error(f"Task failed for {url}: {e}")
        # Production-safe error message - don't expose internal details
        return Result.fail("DOWNLOAD_FAILED", 500).with_message(
            "İndirme işlemi başarısız oldu. Lütfen daha sonra tekrar deneyin."
        ).dict()

