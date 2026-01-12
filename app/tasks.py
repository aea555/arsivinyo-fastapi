from app.celery_app import celery_app
from app.downloader import Downloader
from app.metadata import update_creation_time
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, name="app.tasks.download_media")
def download_media_task(self, url: str):
    """Celery task to download media and update metadata."""
    downloader = Downloader()
    
    try:
        # 1. Download the media
        self.update_state(state='PROGRESS', meta={'status': 'Downloading...'})
        file_path = downloader.download(url)
        
        # 2. Update metadata
        self.update_state(state='PROGRESS', meta={'status': 'Updating metadata...'})
        update_creation_time(file_path)
        
        return {
            "status": "COMPLETED",
            "file_path": file_path,
            "filename": os.path.basename(file_path)
        }
    except Exception as e:
        logger.error(f"Task failed for {url}: {e}")
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise
