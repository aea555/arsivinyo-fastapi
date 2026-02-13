import os


def get_bool_env(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable with safe defaults."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    return default


# Environment
ENV = os.getenv("ENV", "development").strip().lower()
IS_PRODUCTION = ENV == "production"

# Security
APP_SECRET_KEY = os.getenv("APP_SECRET_KEY")
FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

# Explicit toggle for App Check requirement.
# Default: enabled in production, disabled in development.
REQUIRE_FIREBASE_APPCHECK = get_bool_env("REQUIRE_FIREBASE_APPCHECK", default=IS_PRODUCTION)

# Rate Limiting and Download Limits Configuration
# All limits are per-IP basis

# Request rate limit per hour
RATE_LIMIT_REQUESTS_PER_HOUR = 180

# Maximum file size for a single download (in MB)
MAX_FILE_SIZE_MB = 50

# Maximum total download volume per hour (in MB)
MAX_HOURLY_VOLUME_MB = 250

# Maximum file size for VIP downloads (in MB)
# 2GB Safety Limit to prevent disk exhaustion on 40GB VPS
VIP_MAX_FILE_SIZE_MB = 2048
