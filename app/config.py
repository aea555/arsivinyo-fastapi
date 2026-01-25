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
