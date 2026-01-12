import os
import logging
from typing import List, Optional
import random

logger = logging.getLogger(__name__)

class CookieManager:
    """Manages a pool of cookie files for different platforms to avoid being blocked."""
    
    def __init__(self, cookies_dir: str = "cookies"):
        self.cookies_dir = cookies_dir
        if not os.path.exists(cookies_dir):
            os.makedirs(cookies_dir)

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
        logger.info(f"Added cookie file for {platform}: {filename}")

# Global instance
cookie_manager = CookieManager()
