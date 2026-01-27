import os
from typing import List, Optional
import random
from app.logger import get_logger

logger = get_logger(__name__)

class CookieManager:
    """Manages a pool of cookie files for different platforms to avoid being blocked."""
    
    def __init__(self, cookies_dir: str = "cookies"):
        # Resolve absolute path relative to the project root (one level up from app/)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.cookies_dir = os.path.join(base_dir, cookies_dir)
        
        logger.error(f"[COOKIE DEBUG] CookieManager initialized with absolute path: {self.cookies_dir}")
        
        if not os.path.exists(self.cookies_dir):
            try:
                os.makedirs(self.cookies_dir)
                logger.error(f"[COOKIE DEBUG] Created cookies directory at: {self.cookies_dir}")
            except Exception as e:
                logger.error(f"Failed to create cookies directory: {e}")

    def get_cookie_file(self, platform: str) -> Optional[str]:
        """Returns a random cookie file path for the given platform."""
        platform_dir = os.path.join(self.cookies_dir, platform)
        if not os.path.exists(platform_dir):
            return None
        
        cookie_files = [
            os.path.join(platform_dir, f) 
            for f in os.listdir(platform_dir) 
            if f.endswith(".txt") or f.endswith(".json")
        ]
        
        if not cookie_files:
            return None
            
        return random.choice(cookie_files)

    def add_cookie_file(self, platform: str, filename: str, content: str):
        """Adds a new cookie file to the pool."""
        platform_dir = os.path.join(self.cookies_dir, platform)
        if not os.path.exists(platform_dir):
            os.makedirs(platform_dir)
            
        filepath = os.path.join(platform_dir, filename)
        with open(filepath, "w") as f:
            f.write(content)
        logger.error(f"[COOKIE DEBUG] Added cookie file for {platform}: {filename}")

# Global instance
cookie_manager = CookieManager()
