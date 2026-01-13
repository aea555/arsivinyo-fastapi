"""
Locust Load Testing for Media Downloader API

IMPORTANT: This test simulates different IPs using X-Forwarded-For header
to avoid hitting rate limits during load testing.

Install: pip install locust
Run: locust -f tests/locustfile.py --host=http://127.0.0.1:8090
"""

from locust import HttpUser, task, between, events
import random

# Real YouTube shorts for testing
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


def generate_random_ip():
    """Generate a random IP address for load testing."""
    return f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"


class MediaDownloaderUser(HttpUser):
    """
    Simulates a user downloading media.
    Each user gets a unique fake IP to avoid rate limiting.
    """
    
    wait_time = between(3, 8)  # Wait 3-8 seconds between tasks
    
    def on_start(self):
        """Called when a user starts - assign unique IP."""
        self.fake_ip = generate_random_ip()
        self.task_ids = []
        self.downloads_started = 0
        self.downloads_completed = 0
    
    def get_headers(self):
        """Get headers with bypass secret for load testing."""
        return {
            "Content-Type": "application/json",
            "X-Forwarded-For": generate_random_ip(),
            "X-App-Secret": "dev_secret_bypass",  # Bypass all security checks
        }
    
    @task(10)
    def download_video(self):
        """Submit a download request for a random video."""
        url = random.choice(TEST_SHORTS)
        
        with self.client.post(
            "/download",
            json={"url": url},
            headers=self.get_headers(),
            catch_response=True
        ) as response:
            if response.status_code == 202:
                try:
                    data = response.json()
                    if data:
                        task_id = data.get("data", {}).get("task_id")
                        if task_id:
                            self.task_ids.append(task_id)
                            self.downloads_started += 1
                except Exception:
                    pass
                response.success()
            elif response.status_code in [429, 413]:
                # Rate limit or file too large
                response.success()
            else:
                response.failure(f"Unexpected: {response.status_code}")

    @task(5)
    def check_status(self):
        """Check status of a pending download."""
        if not self.task_ids:
            return
        
        task_id = random.choice(self.task_ids)
        
        with self.client.get(
            f"/status/{task_id}",
            headers=self.get_headers(),
            catch_response=True
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    status = data.get("data", {}).get("status")
                    if status == "SUCCESS":
                        self.downloads_completed += 1
                        if task_id in self.task_ids:
                            self.task_ids.remove(task_id)
                except Exception:
                    pass
                response.success()
            else:
                response.failure(f"Status check failed: {response.status_code}")
    
    @task(1)
    def health_check(self):
        """Check API health."""
        with self.client.get("/", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")


class HeavyDownloaderUser(HttpUser):
    """
    Aggressive user making rapid requests.
    Each user gets unique IP to stress test without hitting rate limits.
    """
    
    wait_time = between(1, 2)
    
    def on_start(self):
        self.fake_ip = generate_random_ip()
    
    @task
    def rapid_download(self):
        url = random.choice(TEST_SHORTS)
        
        self.client.post(
            "/download",
            json={"url": url},
            headers={
                "Content-Type": "application/json",
                "X-Forwarded-For": generate_random_ip(),
                "X-App-Secret": "dev_secret_bypass",
            },
        )


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Print summary when test stops."""
    print("\n" + "="*60)
    print("LOAD TEST COMPLETED")
    print("="*60)
    
    stats = environment.stats
    print(f"Total requests: {stats.total.num_requests}")
    print(f"Failures: {stats.total.num_failures}")
    print(f"Avg response time: {stats.total.avg_response_time:.0f}ms")
    print(f"Requests/sec: {stats.total.current_rps:.1f}")
    print("="*60)
