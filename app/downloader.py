import yt_dlp
import os
import logging
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class Downloader:
    def __init__(self, download_path: str = "downloads"):
        self.download_path = download_path
        if not os.path.exists(download_path):
            os.makedirs(download_path)

    def get_info(self, url: str) -> Dict[str, Any]:
        """Extract information from the URL without downloading."""
        from app.cookie_manager import cookie_manager
        
        # Detect platform from URL (very basic detection)
        platform = "youtube" if "youtube" in url or "youtu.be" in url else "generic"
        cookie_file = cookie_manager.get_cookie_file(platform)

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': 'best',
            'cookiefile': cookie_file if cookie_file else None,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                return info
            except Exception as e:
                logger.error(f"Error extracting info for {url}: {e}")
                raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def download(self, url: str, filename: Optional[str] = None) -> str:
        """Download media from the given URL."""
        from app.cookie_manager import cookie_manager
        
        platform = "youtube" if "youtube" in url or "youtu.be" in url else "generic"
        cookie_file = cookie_manager.get_cookie_file(platform)

        # Base options
        ydl_opts = {
            'format': 'best',
            'outtmpl': os.path.join(self.download_path, filename or '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'cookiefile': cookie_file if cookie_file else None,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
                downloaded_file = ydl.prepare_filename(info)
                return downloaded_file
            except Exception as e:
                logger.error(f"Error downloading {url}: {e}")
                raise

    def check_file_size(self, info: Dict[str, Any], limit_mb: int = 10) -> bool:
        """Check if the predicted file size is within limits. Return False if size unknown."""
        filesize = info.get('filesize') or info.get('filesize_approx')
        if filesize:
            size_mb = filesize / (1024 * 1024)
            return size_mb <= limit_mb
        
        # Strict: If we can't determine size, reject it.
        logger.warning(f"Could not determine file size for {info.get('url')}, rejecting.")
        return False
