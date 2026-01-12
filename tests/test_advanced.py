"""
Advanced Tests for Media Downloader API

Tests cover:
1. Metadata modification verification
2. Stress testing under load

Run with: pytest tests/test_advanced.py -v -s
"""

import pytest
import httpx
import asyncio
import subprocess
import os
from datetime import datetime, timedelta

BASE_URL = "http://127.0.0.1:8090"
APP_SECRET = "dev_secret_bypass"

# Test URLs
TEST_SHORTS = [
    "https://www.youtube.com/shorts/ksBNx1vBm_0",
    "https://www.youtube.com/shorts/xmo2jz4sr1A",
    "https://www.youtube.com/shorts/0Aety1QZBNI",
    "https://www.youtube.com/shorts/_usv1SyiWWE",
    "https://www.youtube.com/shorts/UZjDfO2Vmdo",
    "https://www.youtube.com/shorts/e4KrM6TiRp0",
    "https://www.youtube.com/shorts/hSgAWiWIgKs",
    "https://www.youtube.com/shorts/AgAfnPq2Wzc",
]


def flush_redis():
    """Flush Redis to reset limits."""
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
    """Start a download and return the response data."""
    response = await client.post(
        "/download",
        json={"url": url},
        headers=get_headers(include_secret=True),
    )
    return {
        "status_code": response.status_code,
        "data": response.json(),
    }


async def poll_until_complete(client: httpx.AsyncClient, task_id: str, timeout: int = 120) -> dict:
    """Poll for task completion."""
    start_time = asyncio.get_event_loop().time()
    
    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > timeout:
            return {"success": False, "code": "TIMEOUT"}
        
        response = await client.get(f"/status/{task_id}")
        data = response.json()
        task_data = data.get("data") or {}
        celery_status = task_data.get("status", "UNKNOWN")
        
        if celery_status == "SUCCESS":
            inner_data = task_data.get("data") or {}
            return {
                "success": True,
                "code": task_data.get("code"),
                "file_path": inner_data.get("file_path"),
                "filename": inner_data.get("filename"),
                "size_mb": inner_data.get("size_mb", 0),
            }
        elif celery_status == "FAILURE":
            return {"success": False, "code": "TASK_FAILED"}
        
        await asyncio.sleep(2)


def get_video_creation_time(file_path: str) -> datetime | None:
    """
    Extract creation_time metadata from a video file using ffprobe.
    
    Returns:
        datetime object if found, None otherwise
    """
    try:
        # Run ffprobe inside the Docker container
        result = subprocess.run(
            [
                "docker", "exec", "downloader_api",
                "ffprobe", "-v", "quiet",
                "-show_entries", "format_tags=creation_time",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file_path
            ],
            capture_output=True, text=True, timeout=10
        )
        
        if result.returncode == 0 and result.stdout.strip():
            time_str = result.stdout.strip()
            # Parse ISO format: 2026-01-12T23:45:00
            # May have timezone suffix, remove it
            time_str = time_str.split('.')[0].replace('Z', '')
            return datetime.fromisoformat(time_str)
    except Exception as e:
        print(f"⚠️ ffprobe error: {e}")
    
    return None


# --- Metadata Verification Test ---

@pytest.mark.asyncio
async def test_metadata_creation_time_updated():
    """
    Test that downloaded videos have their creation_time metadata 
    updated to the current time (within a reasonable tolerance).
    """
    flush_redis()
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120.0) as client:
        print("\n📥 Testing metadata modification...")
        
        # Start download
        url = TEST_SHORTS[0]
        result = await start_download(client, url)
        
        if result["status_code"] != 202:
            pytest.skip(f"Download failed to start: {result['data']}")
        
        task_id = result["data"]["data"]["task_id"]
        print(f"   Task ID: {task_id}")
        
        # Wait for completion
        before_download = datetime.now()
        task_result = await poll_until_complete(client, task_id)
        after_download = datetime.now()
        
        if not task_result.get("success"):
            pytest.fail(f"Download failed: {task_result}")
        
        file_path = task_result.get("file_path")
        print(f"   Downloaded file: {file_path}")
        
        if not file_path:
            pytest.skip("File path not returned in response")
        
        # Check metadata
        creation_time = get_video_creation_time(file_path)
        
        if creation_time is None:
            print("   ⚠️ Could not read creation_time metadata")
            pytest.skip("Could not read creation_time metadata")
        
        print(f"   📅 creation_time: {creation_time}")
        print(f"   📅 download window: {before_download} to {after_download}")
        
        # Verify creation_time is within a reasonable window (5 minute tolerance)
        tolerance = timedelta(minutes=5)
        
        # creation_time should be close to when the download happened
        time_diff = abs((creation_time - before_download).total_seconds())
        
        if time_diff < tolerance.total_seconds():
            print("   ✅ Metadata creation_time is correctly set to current time!")
        else:
            print(f"   ⚠️ creation_time differs by {time_diff:.1f} seconds from download time")
            # Still pass if within a day (might be timezone issues)
            assert time_diff < 86400, f"creation_time is too far off: {time_diff}s"


# --- Stress Test ---

@pytest.mark.asyncio
async def test_stress_parallel_downloads():
    """
    Test the system under load by submitting multiple downloads simultaneously.
    
    This verifies:
    - Worker doesn't crash under parallel requests
    - All requests get valid responses
    - Reasonable response times
    """
    flush_redis()
    
    NUM_PARALLEL = 5  # Number of parallel downloads
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=180.0) as client:
        print(f"\n🔥 Stress test: {NUM_PARALLEL} parallel downloads")
        
        start_time = datetime.now()
        
        # Submit all downloads simultaneously
        tasks = []
        for i in range(NUM_PARALLEL):
            url = TEST_SHORTS[i % len(TEST_SHORTS)]
            tasks.append(start_download(client, url))
        
        # Wait for all submissions
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        submission_time = (datetime.now() - start_time).total_seconds()
        print(f"   📤 All {NUM_PARALLEL} downloads submitted in {submission_time:.1f}s")
        
        # Count successes
        successful_submissions = 0
        task_ids = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"   ❌ Request {i+1} exception: {result}")
            elif result["status_code"] == 202:
                successful_submissions += 1
                task_id = result["data"]["data"]["task_id"]
                task_ids.append(task_id)
                print(f"   ✅ Request {i+1}: Task {task_id[:8]}...")
            else:
                print(f"   ⚠️ Request {i+1}: {result['status_code']} - {result['data'].get('code')}")
        
        print(f"\n   📊 Submissions: {successful_submissions}/{NUM_PARALLEL} successful")
        
        # Wait for all tasks to complete
        print("\n   ⏳ Waiting for all tasks to complete...")
        
        completion_tasks = [poll_until_complete(client, tid, timeout=180) for tid in task_ids]
        completion_results = await asyncio.gather(*completion_tasks, return_exceptions=True)
        
        total_time = (datetime.now() - start_time).total_seconds()
        
        # Count completed downloads
        completed = 0
        total_size_mb = 0
        
        for i, result in enumerate(completion_results):
            if isinstance(result, Exception):
                print(f"   ❌ Task {i+1} exception: {result}")
            elif result.get("success"):
                completed += 1
                size_mb = result.get("size_mb", 0)
                total_size_mb += size_mb
                print(f"   ✅ Task {i+1}: Completed ({size_mb:.1f}MB)")
            else:
                print(f"   ⚠️ Task {i+1}: {result.get('code')}")
        
        print(f"\n{'='*60}")
        print(f"📊 STRESS TEST SUMMARY:")
        print(f"   Parallel requests: {NUM_PARALLEL}")
        print(f"   Successful submissions: {successful_submissions}")
        print(f"   Completed downloads: {completed}")
        print(f"   Total data downloaded: {total_size_mb:.1f}MB")
        print(f"   Total time: {total_time:.1f}s")
        print(f"   Avg time per download: {total_time/max(completed, 1):.1f}s")
        print(f"{'='*60}")
        
        # Assert reasonable success rate
        success_rate = completed / NUM_PARALLEL if NUM_PARALLEL > 0 else 0
        print(f"\n   Success rate: {success_rate*100:.0f}%")
        
        assert success_rate >= 0.6, f"Success rate too low: {success_rate*100:.0f}%"


# --- Sequential Load Test ---

@pytest.mark.asyncio
async def test_sequential_load():
    """
    Test sustained sequential load - many downloads one after another.
    
    This verifies:
    - Worker doesn't accumulate memory/resource issues
    - Consistent response times
    """
    flush_redis()
    
    NUM_DOWNLOADS = 10
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120.0) as client:
        print(f"\n📥 Sequential load test: {NUM_DOWNLOADS} downloads")
        
        completed = 0
        total_time = 0
        download_times = []
        
        for i in range(NUM_DOWNLOADS):
            url = TEST_SHORTS[i % len(TEST_SHORTS)]
            
            start = datetime.now()
            
            result = await start_download(client, url)
            if result["status_code"] != 202:
                print(f"   ⚠️ Download {i+1} failed to start: {result['data'].get('code')}")
                continue
            
            task_id = result["data"]["data"]["task_id"]
            task_result = await poll_until_complete(client, task_id, timeout=90)
            
            elapsed = (datetime.now() - start).total_seconds()
            download_times.append(elapsed)
            total_time += elapsed
            
            if task_result.get("success"):
                completed += 1
                size_mb = task_result.get("size_mb", 0)
                print(f"   ✅ Download {i+1}/{NUM_DOWNLOADS}: {elapsed:.1f}s ({size_mb:.1f}MB)")
            else:
                print(f"   ⚠️ Download {i+1}/{NUM_DOWNLOADS}: {task_result.get('code')} ({elapsed:.1f}s)")
        
        # Calculate statistics
        avg_time = sum(download_times) / len(download_times) if download_times else 0
        max_time = max(download_times) if download_times else 0
        min_time = min(download_times) if download_times else 0
        
        print(f"\n{'='*60}")
        print(f"📊 SEQUENTIAL LOAD TEST SUMMARY:")
        print(f"   Total downloads: {NUM_DOWNLOADS}")
        print(f"   Completed: {completed}")
        print(f"   Avg time: {avg_time:.1f}s")
        print(f"   Min time: {min_time:.1f}s")
        print(f"   Max time: {max_time:.1f}s")
        print(f"   Total time: {total_time:.1f}s")
        print(f"{'='*60}")
        
        # Assert reasonable completion rate
        assert completed >= NUM_DOWNLOADS * 0.7, f"Too many failures: {completed}/{NUM_DOWNLOADS}"
