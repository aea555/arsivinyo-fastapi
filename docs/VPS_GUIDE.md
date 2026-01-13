# VPS Deployment & Testing Guide

Media Downloader API için 2 vCPU / 4 GB RAM / 40 GB Disk VPS deployment rehberi.

---

## 1. Resource Limits

| Container | Memory | CPU |
|-----------|--------|-----|
| Worker | 1 GB | - |
| API | 512 MB | - |
| Redis | 128 MB | - |
| Nginx | 64 MB | - |
| **Total** | ~1.7 GB | 2 vCPU |

---

## 2. Pre-Deployment Checklist

```bash
# SSH to VPS
ssh user@your-vps-ip

# Install Docker & Docker Compose
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Clone repository
git clone your-repo-url
cd arsivinyo-fastapi

# Create .env file
cp .env.example .env
nano .env  # Edit production values

# Create required directories
mkdir -p downloads cookies
chmod 755 scripts/*.sh
```

---

## 3. Disk Cleanup Cronjob Setup

### 3.1 Initial Setup
```bash
# Test cleanup script manually
./scripts/cleanup_downloads.sh
```

### 3.2 Disk Cleanup Cronjob (CRITICAL)
Since the files are created by Docker (root), the cleanup script **must run as root**.

```bash
# Open root crontab
sudo crontab -e

# Add this line (runs every 30 mins)
*/30 * * * * cd /home/ubuntu/arsivinyo-fastapi && ./scripts/cleanup_downloads.sh >> /var/log/cleanup.log 2>&1
```
# Verify crontab
crontab -l

# Create log file with proper permissions
sudo touch /var/log/cleanup.log
sudo chown $USER:$USER /var/log/cleanup.log

# Test cleanup script manually
./scripts/cleanup_downloads.sh
```

---

## 4. Load Testing on VPS

### 4.1 Start Services
```bash
docker compose up -d --build
sleep 20  # Wait for startup
docker compose ps  # Verify all running
```

### 4.2 Run Monitor (Terminal 1)
```bash
./scripts/monitor_resources.sh
```

### 4.3 Run Locust (Terminal 2 - From local machine)
```bash
# Install locust locally
pip install locust

# Run against VPS
locust -f tests/locustfile.py --host=http://YOUR_VPS_IP:8090
```

Open http://localhost:8089 and configure:
- **Users**: Start with 10, increase to 20-50
- **Spawn Rate**: 2 users/second
- **Run Time**: 5-10 minutes

---

## 5. Evaluating Test Results

### 5.1 Success Criteria ✅

| Metric | Target | Critical |
|--------|--------|----------|
| Response Time (median) | < 1s | < 5s |
| Error Rate | < 5% | < 10% |
| Memory Usage | < 80% | < 95% |
| CPU Usage | < 70% | < 90% |
| Disk Usage | < 70% | < 85% |

### 5.2 Warning Signs ⚠️

1. **Memory > 80%**: Reduce `--concurrency` in worker
2. **CPU > 80%**: Reduce concurrent users or add rate limiting
3. **Disk > 70%**: Decrease `MAX_AGE_MINUTES` in cleanup script
4. **Response Time > 5s**: Check worker logs, reduce concurrency
5. **Error Rate > 10%**: Check logs, likely rate limiting or crashes

### 5.3 Reading Monitor Output

```
📊 CONTAINER RESOURCES:
NAME              CPU %   MEMORY              NET I/O
downloader_worker 45%     512MiB / 1GiB       ← Should stay < 800MiB
downloader_api    10%     256MiB / 512MiB     ← Should stay < 400MiB
downloader_redis  2%      50MiB / 128MiB      ← Should stay < 100MiB
```

### 5.4 Common Issues & Solutions

| Issue | Symptom | Solution |
|-------|---------|----------|
| Worker OOM | Container restarts | Reduce `--concurrency` to 1 |
| Disk Full | 429 errors | Run cleanup, decrease age limit |
| Slow Downloads | High response time | Check network, reduce concurrent |
| Rate Limit Hit | 429 errors | Expected under heavy load |

---

## 6. Production Monitoring

### 6.1 Quick Health Check
```bash
# Check containers running
docker compose ps

# Check recent logs
docker compose logs --tail=50

# Check disk usage
df -h

# Check download folder size
du -sh downloads/
```

### 6.2 Log Rotation
```bash
# Add to /etc/logrotate.d/media-downloader
/var/log/cleanup.log {
    weekly
    rotate 4
    compress
    missingok
    notifempty
}
```

---

## 7. Recommended VPS Specs by Load

| Daily Downloads | vCPU | RAM | Disk | Worker Concurrency |
|-----------------|------|-----|------|-------------------|
| < 1000 | 2 | 4 GB | 40 GB | 2 |
| 1000-5000 | 4 | 8 GB | 80 GB | 4 |
| 5000+ | 8 | 16 GB | 160 GB | 8 |
