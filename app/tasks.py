from app.celery_app import celery_app
from app.downloader import Downloader
from app.metadata import update_creation_time
from app.schemas.result import Result
from app.redis_client import redis_client
from app.schemas.result import Result
from app.redis_client import redis_client
from app.config import MAX_FILE_SIZE_MB, VIP_MAX_FILE_SIZE_MB
import os
import shutil
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
def download_media_task(self, url: str, client_ip: str = "unknown", is_vip: bool = False):
    """Celery task to download media and update metadata."""
    downloader = Downloader()
    
    try:
        # 1. Extract info FIRST to check file size
        self.update_state(state='PROGRESS', meta={'status': 'Checking file size...'})
        info = downloader.get_info(url)
        
        if is_vip:
            logger.info(f"VIP Task: Using expanded limit ({VIP_MAX_FILE_SIZE_MB}MB) for {url}")
            limit = VIP_MAX_FILE_SIZE_MB
        else:
            limit = MAX_FILE_SIZE_MB
        
        # 2. Enforce file size limit
        if not downloader.check_file_size(info, limit_mb=limit):
            filesize = info.get('filesize') or info.get('filesize_approx') or 0
            size_mb = filesize / (1024 * 1024) if filesize else 0
            error_msg = f"File size ({size_mb:.1f}MB) exceeds limit ({limit}MB)"
            logger.warning(f"Rejecting download for {url}: {error_msg}")
            return Result.fail("FILE_TOO_LARGE", 413).with_message(error_msg).dict()

        # 3. PHYSICAL SAFETY CHECK: Check disk space
        # We need ~2.5x the file size for temporary files during merge
        try:
            total, used, free = shutil.disk_usage(downloader.download_path)
            # Estimate size again (downloader.check_file_size logged it, but we need the value)
            est_size_mb, _ = downloader.estimate_file_size_mb(info)
            if est_size_mb > 0:
                required_mb = est_size_mb * 2.5
                free_mb = free / (1024 * 1024)
                if free_mb < required_mb:
                    logger.critical(f"DISK SPACE CRITICAL: Free={free_mb:.1f}MB, Required={required_mb:.1f}MB")
                    return Result.fail("SERVER_BUSY", 503).with_message("Sunucu yoğun, lütfen daha sonra tekrar deneyin.").dict()
        except Exception as e:
            logger.error(f"Failed to check disk space: {e}")
        
        # 4. Download the media
        self.update_state(state='PROGRESS', meta={'status': 'Downloading...'})
        file_path = downloader.download(url, is_vip=is_vip)
        
        # 5. Update metadata
        self.update_state(state='PROGRESS', meta={'status': 'Updating metadata...'})
        update_creation_time(file_path)
        
        # 6. Track volume for hourly limit
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

