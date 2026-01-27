from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# Supported platforms - only these will be accepted for downloads
SUPPORTED_PLATFORMS = {
    "twitter": ["twitter.com", "x.com"],
    "instagram": ["instagram.com"],
    "facebook": ["facebook.com", "fb.watch"],
    "reddit": ["reddit.com"],
    "youtube": ["youtube.com", "youtu.be"],
}


def validate_supported_platform(url: str) -> str:
    """
    Validates that the URL is from a supported platform.
    
    Returns:
        The platform name if valid (twitter, instagram, facebook, reddit)
    
    Raises:
        ValueError: If the platform is not supported
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    
    # Remove 'www.' prefix for matching
    if domain.startswith("www."):
        domain = domain[4:]
    
    for platform, domains in SUPPORTED_PLATFORMS.items():
        for d in domains:
            if d in domain:
                return platform
    
    raise ValueError(
        "Bu platform desteklenmiyor. Desteklenen platformlar: Twitter, Instagram, Facebook, Reddit"
    )


def clean_youtube_url(url: str) -> str:
    """
    Cleans YouTube URLs:
    1. Extracts 'v' parameter (video ID).
    2. Removes playlist-related params ('list', 'index', 'start_radio', 'rv').
    3. Reconstructs a clean video URL.
    4. Raises ValueError if it's a playlist URL without a video ID.
    5. Handles YouTube Shorts properly.
    """
    parsed = urlparse(url)
    
    # Check if it is a YouTube URL
    if "youtube.com" not in parsed.netloc and "youtu.be" not in parsed.netloc:
        return url
        
    # Handle short URLs (youtu.be/ID)
    if "youtu.be" in parsed.netloc:
        # Path is /ID
        return url
        
    # Handle /shorts/ID URLs
    if "/shorts/" in parsed.path:
        # Already clean enough, just strip query params if any
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))

    query_params = parse_qs(parsed.query)
    
    # Check if it has a video ID ('v')
    if 'v' in query_params:
        video_id = query_params['v'][0]
        # Reconstruct pure video URL
        return f"https://www.youtube.com/watch?v={video_id}"
    
    # If no 'v' but has 'list', it's a pure playlist page -> REJECT
    if 'list' in query_params:
        raise ValueError("Playlist downloads are not supported. Please provide a single video URL.")
        
    # If neither, just return original (might be channel page or something else, let yt-dlp handle or fail)
    return url

# def clean_tiktok_url(url: str) -> str:
#     """
#     Cleans TikTok URLs:
#     Removes tracking parameters (is_from_webapp, sender_device, etc.)
#     """
#     parsed = urlparse(url)
#     
#     if "tiktok.com" not in parsed.netloc:
#         return url
#         
#     # Reconstruct URL without query parameters
#     # TikTok URLs are typically https://www.tiktok.com/@user/video/ID
#     # We strip entirely the query string
#     return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
