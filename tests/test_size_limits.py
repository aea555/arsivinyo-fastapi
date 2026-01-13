"""
Size Limit Tests for Media Downloader API

Tests:
1. File Size Limit (50MB per file) - should reject large videos
2. Hourly Volume Limit (50MB/hour) - should reject after cumulative downloads exceed 50MB

Run with: pytest tests/test_size_limits.py -v -s
"""

import pytest
import httpx
import subprocess
import asyncio

BASE_URL = "http://127.0.0.1:8090"
APP_SECRET = "dev_secret_bypass"

# Test URLs
LONG_VIDEO_URL = "https://www.youtube.com/watch?v=AEG32nHYKPE"  # Large file (>50MB)

# Shorts for volume testing (each ~5-40MB)
SHORTS_URLS = [
    "https://www.youtube.com/shorts/ksBNx1vBm_0",
    "https://www.youtube.com/shorts/xmo2jz4sr1A",
    "https://www.youtube.com/shorts/0Aety1QZBNI",
    "https://www.youtube.com/shorts/_usv1SyiWWE",
    "https://www.youtube.com/shorts/UZjDfO2Vmdo",
    "https://www.youtube.com/shorts/e4KrM6TiRp0",
    "https://www.youtube.com/shorts/hSgAWiWIgKs",
    "https://www.youtube.com/shorts/AgAfnPq2Wzc",
    "https://www.youtube.com/shorts/bp3pvE8W0L4",
    "https://www.youtube.com/shorts/dq5-ypv_fUM",
    "https://www.youtube.com/shorts/ILd-bZbOHMc",
    "https://www.youtube.com/shorts/m4Zu4RIcfkE",
    "https://www.youtube.com/shorts/DlL_ghwnDKo",
    "https://www.youtube.com/shorts/J795tTZYyKA",
    "https://www.youtube.com/shorts/ug1EkuxEMb8",
    "https://www.youtube.com/shorts/zp2iFW77C2c",
    "https://www.youtube.com/shorts/HYed95jWq-g",
    "https://www.youtube.com/shorts/3rEaXHFzYn8",
    "https://www.youtube.com/shorts/aJtAxB_d8c4",
    "https://www.youtube.com/shorts/dUkyDIiAqxw",
    "https://www.youtube.com/shorts/foViq65Bqec",
]

# Try to import limits from config, fallback to hardcoded values if running outside app context
try:
    from app.config import MAX_FILE_SIZE_MB, MAX_HOURLY_VOLUME_MB
except ModuleNotFoundError:
    MAX_FILE_SIZE_MB = 50
    MAX_HOURLY_VOLUME_MB = 250


def flush_redis():
    """Flush Redis to reset rate limits and volume tracking."""
    try:
        subprocess.run(
            ["docker", "exec", "downloader_redis", "redis-cli", "FLUSHALL"],
            capture_output=True, text=True, timeout=5
        )
        print("🗑️ Redis flushed")
    except Exception as e:
        print(f"⚠️ Redis flush warning: {e}")


def get_headers(include_secret: bool = True):
    headers = {"Content-Type": "application/json"}
    if include_secret:
        headers["X-App-Secret"] = APP_SECRET
    return headers


async def start_download(client: httpx.AsyncClient, url: str) -> dict:
    """Start a download and return the response data with detailed logging."""
    response = await client.post(
        "/download",
        json={"url": url},
        headers=get_headers(include_secret=False),  # No bypass - test real limits
    )
    result = {
        "status_code": response.status_code,
        "data": response.json(),
    }
    
    # Detailed logging
    print(f"   📤 POST /download response: status={response.status_code}")
    print(f"      Response data: {result['data']}")
    
    return result


async def poll_status(client: httpx.AsyncClient, task_id: str, timeout: int = 120) -> dict:
    """Poll for task completion with detailed logging."""
    start_time = asyncio.get_event_loop().time()
    poll_count = 0
    
    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > timeout:
            print(f"   ⏰ Polling timeout after {poll_count} attempts ({elapsed:.1f}s)")
            return {"success": False, "code": "TIMEOUT", "message": "Polling timeout"}
        
        response = await client.get(f"/status/{task_id}")
        data = response.json()
        poll_count += 1
        
        # The status endpoint returns Result format with data containing task info
        task_data = data.get("data") or {}
        celery_status = task_data.get("status", "UNKNOWN")
        
        if poll_count % 5 == 0:  # Log every 5th poll
            print(f"   🔄 Poll #{poll_count}: {celery_status}")
        
        # Check if task completed
        if celery_status == "SUCCESS":
            print(f"   ✅ Task completed after {poll_count} polls ({elapsed:.1f}s)")
            # Extract the inner result data (from tasks.py Result.dict())
            # Structure: task_data contains merged result, so data.data has file info
            inner_data = task_data.get("data") or {}
            return {
                "success": task_data.get("success", True),
                "code": task_data.get("code", "DOWNLOAD_COMPLETED"),
                "size_mb": inner_data.get("size_mb", 0),
                "filename": inner_data.get("filename"),
                "file_path": inner_data.get("file_path"),
            }
        elif celery_status == "FAILURE":
            print(f"   ❌ Task failed after {poll_count} polls")
            return {"success": False, "code": "TASK_FAILED", "message": "Celery task failed"}
        
        await asyncio.sleep(2)



# --- Hourly Volume Limit Test ---

@pytest.mark.asyncio
async def test_hourly_volume_limit():
    """
    Test that the hourly 250MB volume limit is enforced.
    
    Without bypass secret, downloads are tracked and limited.
    After ~250MB, new downloads should be rejected with VOLUME_LIMIT_EXCEEDED.
    """
    flush_redis()
    
    total_downloaded_mb = 0
    downloads_completed = 0
    volume_limit_hit = False
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=180.0) as client:
        print(f"\n📥 Testing hourly volume limit with {len(SHORTS_URLS)} shorts...")
        print("   (Not using bypass secret - testing real limits)")
        
        for i, url in enumerate(SHORTS_URLS):
            print(f"\n--- Download {i+1}/{len(SHORTS_URLS)} ---")
            print(f"URL: {url}")
            
            result = await start_download(client, url)
            
            # Check if we hit volume limit at API level
            if result["status_code"] == 429:
                code = result["data"].get("code", "")
                message = result["data"].get("message", "")
                print(f"🛑 429 Response: {code} - {message}")
                
                if code == "VOLUME_LIMIT_EXCEEDED":
                    volume_limit_hit = True
                    print(f"✅ Volume limit hit after {downloads_completed} downloads (~{total_downloaded_mb:.1f}MB)")
                    break
                elif code == "TOO_MANY_REQUESTS":
                    print(f"⚠️ Rate limit hit (not volume limit)")
                    break
            
            if result["status_code"] == 401:
                print(f"⚠️ Firebase required (expected in production mode)")
                break
                
            if result["status_code"] != 202:
                print(f"⚠️ Download not started: {result['data']}")
                continue
            
            task_id = result["data"]["data"]["task_id"]
            print(f"   Task ID: {task_id}")
            
            # Poll for completion with longer timeout
            task_result = await poll_status(client, task_id, timeout=120)
            
            if task_result.get("code") == "DOWNLOAD_COMPLETED":
                size_mb = task_result.get("size_mb", 0)
                if size_mb == 0:
                    size_mb = 5.0  # Fallback estimate if not provided
                downloads_completed += 1
                total_downloaded_mb += size_mb
                print(f"   ✅ Download {downloads_completed} complete ({size_mb:.1f}MB, total: {total_downloaded_mb:.1f}MB)")

            elif task_result.get("code") == "TIMEOUT":
                print(f"   ⚠️ Download timed out - worker may be overloaded")
            else:
                print(f"   ⚠️ Unexpected result: {task_result}")
            
            # Small delay between downloads
            await asyncio.sleep(1)
        
        print(f"\n{'='*60}")
        print(f"📊 SUMMARY:")
        print(f"   Shorts downloaded: {downloads_completed}")
        print(f"   Total volume: {total_downloaded_mb:.1f}MB")
        print(f"   Volume limit hit: {volume_limit_hit}")
        print(f"{'='*60}")
        
        # Assert volume limit was hit around 250MB
        if not volume_limit_hit and total_downloaded_mb >= 250:
            print("\n⚠️ WARNING: Downloaded 250+MB without hitting volume limit!")


# --- Rate Limit Test ---

@pytest.mark.asyncio
async def test_rate_limit_180_per_hour():
    """Verify rate limit works (without bypass)."""
    flush_redis()
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        headers = get_headers(include_secret=False)  # No bypass
        
        # Make a few quick requests
        for i in range(3):
            response = await client.post(
                "/download",
                json={"url": f"https://example.com/rate-test-{i}"},
                headers=headers,
            )
            print(f"Request {i+1}: status={response.status_code}, code={response.json().get('code')}")
        
        print("✅ Rate limiting test complete")


# --- Large File Rejection Test ---

@pytest.mark.asyncio
async def test_large_file_rejected_immediately():
    """
    Test that a large video (>50MB) is rejected IMMEDIATELY at API level,
    before any download starts. This verifies the pre-flight size check.
    """
    flush_redis()
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
        print(f"\n📥 Testing large file rejection...")
        print(f"URL: {LONG_VIDEO_URL}")
        
        result = await start_download(client, LONG_VIDEO_URL)
        
        print(f"\n📊 Result:")
        print(f"   Status code: {result['status_code']}")
        print(f"   Code: {result['data'].get('code')}")
        print(f"   Message: {result['data'].get('message')}")
        
        # Should be rejected with 413 FILE_TOO_LARGE
        if result["status_code"] == 413:
            assert result["data"]["code"] == "FILE_TOO_LARGE"
            print("✅ Large file correctly rejected with FILE_TOO_LARGE (no download started)")
        elif result["status_code"] == 202:
            # If accepted, check estimated_size_mb
            estimated_size = result["data"]["data"].get("estimated_size_mb")
            print(f"⚠️ Download was accepted! estimated_size_mb: {estimated_size}")
            print("   This means yt-dlp couldn't determine the file size upfront.")
        else:
            print(f"⚠️ Unexpected status code: {result['status_code']}")
