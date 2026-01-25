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
        # --- DEPRECATED: TikTok is no longer supported ---
        if "youtube" in url or "youtu.be" in url:
            platform = "youtube"
        elif "twitter.com" in url or "x.com" in url:
            platform = "twitter"
        elif "instagram.com" in url:
            platform = "instagram"
        # elif "tiktok.com" in url:
        #     platform = "tiktok"
        elif "reddit.com" in url:
            platform = "reddit"
        elif "facebook.com" in url or "fb.watch" in url:
            platform = "facebook"
        else:
            platform = "generic"
        cookie_file = cookie_manager.get_cookie_file(platform)

        # Retrieve advanced configuration from environment
        proxy_url = os.getenv("PROXY_URL")
        po_token = os.getenv("YOUTUBE_PO_TOKEN")
        visitor_data = os.getenv("YOUTUBE_VISITOR_DATA")
        
        if proxy_url:
            logger.info(f"Using Proxy: {proxy_url}")
        
        # Debug: Log cookie file path and existence - ESCALATED TO ERROR FOR DEBUGGING
        if cookie_file:
            import os as _os
            cookie_exists = _os.path.exists(cookie_file)
            logger.error(f"[COOKIE DEBUG] Platform: {platform}, File: {cookie_file}, Exists: {cookie_exists}")
            if not cookie_exists:
                logger.error(f"[COOKIE DEBUG] Cookie file does not exist! CWD: {_os.getcwd()}")
        else:
            logger.error(f"[COOKIE DEBUG] No cookie file found for platform: {platform}")

        # Custom options based on platform
        format_selector = 'best[filesize<50M]/best[filesize_approx<50M]/best'
        
        # --- DEPRECATED: TikTok is no longer supported ---
        # if platform == "tiktok":
        #      # Force H.264 (avc) for TikTok to ensure preview compatibility
        #      # Use bestvideo+bestaudio to ensure we get both streams if separated
        #     format_selector = "best[ext=mp4][vcodec^=avc][acodec!=none]/best[ext=mp4]/best"
        if platform == "reddit":
            # Reddit usually uses DASH/HLS, so we need to validly merge audio+video
            # Metadata is often missing, so we drop filesize constraints to avoid 'No format available'
            format_selector = 'bestvideo+bestaudio/best'
             
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            # 'format': format_selector, # Disable format selector for get_info to ensure we get metadata
            'cookiefile': cookie_file if cookie_file else None,
            'noplaylist': True, 
            'no_cache_dir': True, # crucial to avoid using cached, banned signatures
            'proxy': proxy_url if proxy_url else None,
        }
        
        # --- DEPRECATED: YouTube is no longer supported ---
        # if platform == "youtube":
        #     ydl_opts['extractor_args'] = {'youtube': {'player_client': ['ios']}}
        #     ydl_opts['sleep_interval_requests'] = 1  # 1 second between API requests
        # Advanced Client Strategy: Rotate clients AND header/cookie modes
        # Sometimes sending cookies causes the block (IP mismatch), so we try without them too.
        strategies = [
            ('android', True),
            ('ios', True),
            ('tv_embedded', True),
            ('web', True),
            ('android', False), # Try without cookies (Incognito)
            ('web', False),     # Try web without cookies
        ]

        last_exception = None

        for client, use_cookies in strategies:
            # Prepare options for this strategy
            current_opts = ydl_opts.copy()
            
            if client:
                logger.error(f"[CLIENT DEBUG] Attempting info extraction with client: {client}, cookies={use_cookies}")
                
                # Construct extractor_args
                extractor_args = {'youtube': {'player_client': [client]}}
                
                # Inject PoT / Visitor Data for 'web' client if available
                if client == 'web' and (po_token or visitor_data):
                    if po_token:
                        logger.info("Injecting PO Token into web client args")
                        extractor_args['youtube']['po_token'] = [f"web+{po_token}"]
                    if visitor_data:
                        logger.info("Injecting Visitor Data into web client args")
                        extractor_args['youtube']['visitor_data'] = [visitor_data]
                        
                current_opts['extractor_args'] = extractor_args
            
            if not use_cookies:
                 current_opts['cookiefile'] = None
                 logger.error(f"[COOKIE DEBUG] Strategy requires NO cookies. Unsetting cookiefile.")
            else:
                 # Ensure cookie file is set if available
                 if cookie_file:
                     current_opts['cookiefile'] = cookie_file
                     logger.error(f"[COOKIE DEBUG] Strategy using cookie file: {cookie_file}")
                 else:
                     logger.error(f"[COOKIE DEBUG] Strategy requested cookies but none available.")

            try:
                with yt_dlp.YoutubeDL(current_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    
                    # Handle quote tweets / multiple media
                    if 'entries' in info and info['entries']:
                        logger.info(f"Multiple entries detected ({len(info['entries'])}), using first (main) entry")
                        info = info['entries'][0]
                    
                    return info
            except Exception as e:
                # If this was the last strategy, raise the error
                if (client, use_cookies) == strategies[-1]:
                    logger.error(f"All strategies failed. Last error: {e}")
                    raise
                
                logger.warning(f"Info extraction failed with client {client} (cookies={use_cookies}): {e}. Retrying...")
                last_exception = e
                continue

        if last_exception:
            raise last_exception

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
        
        # --- DEPRECATED: TikTok is no longer supported ---
        if "youtube" in url or "youtu.be" in url:
            platform = "youtube"
        elif "twitter.com" in url or "x.com" in url:
            platform = "twitter"
        elif "instagram.com" in url:
            platform = "instagram"
        # elif "tiktok.com" in url:
        #     platform = "tiktok"
        elif "reddit.com" in url:
            platform = "reddit"
        elif "facebook.com" in url or "fb.watch" in url:
            platform = "facebook"
        else:
            platform = "generic"
        cookie_file = cookie_manager.get_cookie_file(platform)

        # Retrieve advanced configuration from environment
        proxy_url = os.getenv("PROXY_URL")
        po_token = os.getenv("YOUTUBE_PO_TOKEN")
        visitor_data = os.getenv("YOUTUBE_VISITOR_DATA")
        
        if proxy_url:
            logger.info(f"Using Proxy: {proxy_url}")

        # Base options - prefer formats with known size, limit to 50MB
        format_selector = 'best[filesize<50M]/best[filesize_approx<50M]/best'
        
        # --- DEPRECATED: TikTok is no longer supported ---
        # if platform == "tiktok":
        #      # Force H.264 (avc) for TikTok
        #      format_selector = 'bestvideo[vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        if platform == "reddit":
            format_selector = 'bestvideo+bestaudio/best'

        ydl_opts = {
            'format': format_selector,
            'outtmpl': os.path.join(self.download_path, filename or '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'cookiefile': cookie_file if cookie_file else None,
            'noplaylist': True, # Explicitly disable playlist processing
            'merge_output_format': 'mp4', # Ensure final container is MP4 (fixes black screen/audio-only issues)
            'no_cache_dir': True, # crucial
            'proxy': proxy_url if proxy_url else None,
        }
        
        # Advanced Client Strategy: Rotate clients AND header/cookie modes
        strategies = [
            ('android', True),
            ('ios', True),
            ('tv_embedded', True),
            ('web', True),
            ('android', False), # Try without cookies (Incognito)
            ('web', False),     # Try web without cookies
        ]

        last_exception = None

        for client, use_cookies in strategies:
            # Prepare options for this strategy
            current_opts = ydl_opts.copy() # important copy
            
            if client:
                logger.error(f"[CLIENT DEBUG] Attempting download with client: {client}, cookies={use_cookies}")
                
                # Construct extractor_args
                extractor_args = {'youtube': {'player_client': [client]}}
                
                # Inject PoT / Visitor Data for 'web' client if available
                if client == 'web' and (po_token or visitor_data):
                    if po_token:
                        logger.info("Injecting PO Token into web client args")
                        extractor_args['youtube']['po_token'] = [f"web+{po_token}"]
                    if visitor_data:
                        logger.info("Injecting Visitor Data into web client args")
                        extractor_args['youtube']['visitor_data'] = [visitor_data]
                        
                current_opts['extractor_args'] = extractor_args
                
                # Inject PoT / Visitor Data for 'web' client if available
                # These are CRITICAL for bypassing "Sign in to confirm you're not a bot"
                if client == 'web' and (po_token or visitor_data):
                    web_args = extractor_args['youtube'].get('player_client', [])
                    
                    if po_token:
                        logger.info("Injecting PO Token into web client args")
                        extractor_args['youtube']['po_token'] = [f"web+{po_token}"]
                    
                    if visitor_data:
                        logger.info("Injecting Visitor Data into web client args")
                        extractor_args['youtube']['visitor_data'] = [visitor_data]
                        
                current_opts['extractor_args'] = extractor_args
            
            if not use_cookies:
                 current_opts['cookiefile'] = None
            else:
                 if cookie_file:
                     current_opts['cookiefile'] = cookie_file

            try:
                with yt_dlp.YoutubeDL(current_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    
                    # Handle quote tweets / multiple media: use only the first (main) entry
                    if 'entries' in info and info['entries']:
                        logger.info(f"Multiple entries detected in download ({len(info['entries'])}), using first entry")
                        info = info['entries'][0]
                    
                    downloaded_file = None

                    # 1) Most reliable: yt-dlp tells you exactly what it wrote
                    req = info.get("requested_downloads") or []
                    for r in reversed(req):
                        fp = r.get("filepath")
                        if fp and os.path.exists(fp):
                            downloaded_file = fp
                            break

                    # 2) Fallbacks
                    if not downloaded_file:
                        fp = info.get("filepath") or info.get("_filename")
                        if fp and os.path.exists(fp):
                            downloaded_file = fp

                    # 3) Last resort: use prepare_filename, but also prefer a merged .mp4 if it exists
                    if not downloaded_file:
                        cand = ydl.prepare_filename(info)
                        base, _ = os.path.splitext(cand)
                        mp4_cand = base + ".mp4"
                        if os.path.exists(mp4_cand):
                            downloaded_file = mp4_cand
                        else:
                            downloaded_file = cand

                    logger.info(
                        f"Downloaded: ext={info.get('ext')} "
                        f"format_id={info.get('format_id')} "
                        f"requested={[(d.get('ext'), d.get('filepath')) for d in (info.get('requested_downloads') or [])]}"
                    )

                    return downloaded_file

            except Exception as e:
                # If this was the last strategy, raise the error
                if (client, use_cookies) == strategies[-1]:
                    logger.error(f"Downloader failed all strategies. Last error: {e}")
                    raise
                
                logger.warning(f"Download failed with client {client} (cookies={use_cookies}): {e}. Retrying...")
                last_exception = e
                continue

        if last_exception:
            raise last_exception

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
