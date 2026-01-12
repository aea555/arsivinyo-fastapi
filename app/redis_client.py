import redis
import os
from typing import Optional
from app.logger import get_logger

logger = get_logger(__name__)

class RedisClient:
    _instance: Optional['RedisClient'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisClient, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", 6379))
        redis_db = int(os.getenv("REDIS_DB", 0))
        redis_password = os.getenv("REDIS_PASSWORD", None)

        try:
            self.client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
                decode_responses=True,
                socket_timeout=2
            )
            self.client.ping()
            self._initialized = True
            logger.info(f"Connected to Redis at {redis_host}:{redis_port}")
        except redis.ConnectionError as e:
            logger.error(f"Could not connect to Redis: {e}")
            self.client = None

    def is_available(to_self) -> bool:
        if not to_self.client:
            return False
        try:
            return to_self.client.ping()
        except:
            return False

# Global singleton instance
redis_client = RedisClient()
