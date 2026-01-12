import yt_dlp
import os
from typing import Dict, Any, Optional, Tuple

from tenacity import retry, stop_after_attempt, wait_exponential
from app.logger import get_logger

logger = get_logger(__name__)

class Downloader:
    def __init__(self, download_path: str = "downloads"):
        self.download_path = download_path
        if not os.path.exists(download_path):
            os.makedirs(download_path)

    def get_info(self, url: str) -> Dict[str, Any]:
        """Extract information from the URL without downloading."""
        from app.cookie_manager import cookie_manager
        
        # Detect platform from URL
        if "youtube" in url or "youtu.be" in url:
            platform = "youtube"
        elif "twitter.com" in url or "x.com" in url:
            platform = "twitter"
        elif "instagram.com" in url:
            platform = "instagram"
        elif "tiktok.com" in url:
            platform = "tiktok"
        elif "reddit.com" in url:
            platform = "reddit"
        elif "facebook.com" in url or "fb.watch" in url:
            platform = "facebook"
        else:
            platform = "generic"
        cookie_file = cookie_manager.get_cookie_file(platform)

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            # Prefer formats with known filesize, limit to 50MB
            'format': 'best[filesize<50M]/best[filesize_approx<50M]/best',
            'cookiefile': cookie_file if cookie_file else None,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                return info
            except Exception as e:
                logger.error(f"Error extracting info for {url}: {e}")
                raise

    def estimate_file_size_mb(self, info: Dict[str, Any]) -> Tuple[float, str]:
        """
        Estimate file size in MB using multiple methods.
        
        Returns:
            Tuple of (estimated_size_mb, method_used)
            method_used: 'filesize', 'filesize_approx', 'duration_bitrate', 'formats_sum', 'unknown'
        """
        # Method 1: Direct filesize from selected format
        filesize = info.get('filesize')
        if filesize and filesize > 0:
            return filesize / (1024 * 1024), 'filesize'
        
        # Method 2: Approximate filesize
        filesize_approx = info.get('filesize_approx')
        if filesize_approx and filesize_approx > 0:
            return filesize_approx / (1024 * 1024), 'filesize_approx'
        
        # Method 3: Calculate from duration and bitrate (tbr = total bitrate in kbps)
        duration = info.get('duration')  # seconds
        tbr = info.get('tbr')  # total bitrate in kbps
        if duration and tbr:
            # size = (bitrate_kbps * duration_seconds) / 8 / 1024 = MB
            size_mb = (tbr * duration) / 8 / 1024
            return size_mb, 'duration_bitrate'
        
        # Method 4: Sum video and audio format sizes (for DASH)
        formats = info.get('formats', [])
        if formats:
            # Find best video and audio formats with known sizes
            video_size = 0
            audio_size = 0
            
            for fmt in formats:
                fmt_size = fmt.get('filesize') or fmt.get('filesize_approx') or 0
                vcodec = fmt.get('vcodec', 'none')
                acodec = fmt.get('acodec', 'none')
                
                # Video only format
                if vcodec != 'none' and acodec == 'none':
                    if fmt_size > video_size:
                        video_size = fmt_size
                # Audio only format
                elif acodec != 'none' and vcodec == 'none':
                    if fmt_size > audio_size:
                        audio_size = fmt_size
            
            if video_size > 0 or audio_size > 0:
                total_size = video_size + audio_size
                return total_size / (1024 * 1024), 'formats_sum'
        
        # Method 5: Estimate from duration with average bitrate assumption
        if duration:
            # Assume average 2 Mbps for YouTube shorts, 5 Mbps for regular videos
            is_shorts = duration < 180  # Less than 3 minutes
            avg_bitrate_kbps = 2000 if is_shorts else 5000
            size_mb = (avg_bitrate_kbps * duration) / 8 / 1024
            return size_mb, 'duration_estimate'
        
        return 0, 'unknown'

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def download(self, url: str, filename: Optional[str] = None) -> str:
        """Download media from the given URL."""
        from app.cookie_manager import cookie_manager
        
        if "youtube" in url or "youtu.be" in url:
            platform = "youtube"
        elif "twitter.com" in url or "x.com" in url:
            platform = "twitter"
        elif "instagram.com" in url:
            platform = "instagram"
        elif "tiktok.com" in url:
            platform = "tiktok"
        elif "reddit.com" in url:
            platform = "reddit"
        elif "facebook.com" in url or "fb.watch" in url:
            platform = "facebook"
        else:
            platform = "generic"
        cookie_file = cookie_manager.get_cookie_file(platform)

        # Base options - prefer formats with known size, limit to 50MB
        ydl_opts = {
            'format': 'best[filesize<50M]/best[filesize_approx<50M]/best',
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

    def check_file_size(self, info: Dict[str, Any], limit_mb: int = 50) -> bool:
        """Check if the predicted file size is within limits.
        
        Returns:
            True if size is within limit OR if size cannot be determined (permissive mode)
            False only if size is known AND exceeds limit
        """
        size_mb, method = self.estimate_file_size_mb(info)
        
        if size_mb > 0:
            logger.info(f"Estimated file size: {size_mb:.1f}MB (method: {method})")
            if size_mb > limit_mb:
                logger.warning(f"File size {size_mb:.1f}MB exceeds {limit_mb}MB limit")
                return False
            return True
        
        # Permissive: If we can't determine size, allow it but log a warning
        logger.warning(f"Could not determine file size for {info.get('title', 'unknown')}, allowing download")
        return True
