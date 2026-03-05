# Postman API Testing Guide

This guide explains how to test the Media Downloader API using Postman.

## 1. Import Collection

1. Open Postman.
2. Click **Import**.
3. Import `docs/postman_collection.json`.

## 2. Configure Environment

The collection uses `{{base_url}}`.

For local Docker setup:
- `http://127.0.0.1:8090` (Nginx gateway, recommended)
- `http://127.0.0.1:8001` (direct API container port)

For VPS:
- `http://YOUR_VPS_IP:8090`

## 3. Endpoints

### Health Check
- **GET** `/`
- Expected code: `API_READY`

### Start Download
- **POST** `/download`
- Body:
  ```json
  {
    "url": "https://www.youtube.com/shorts/..."
  }
  ```
- Success (`202`):
  ```json
  {
    "success": true,
    "code": "DOWNLOAD_STARTED",
    "status_code": 202,
    "data": {
      "task_id": "...",
      "estimated_size_mb": 12.3
    }
  }
  ```

### Check Task Status
- **GET** `/status/:taskId`
- In progress (`200`):
  ```json
  {
    "success": true,
    "code": "TASK_IN_PROGRESS",
    "status_code": 200,
    "data": {
      "task_id": "...",
      "status": "PENDING"
    }
  }
  ```
- Completed (`200`):
  ```json
  {
    "success": true,
    "code": "TASK_COMPLETED",
    "status_code": 200,
    "data": {
      "task_id": "...",
      "status": "SUCCESS",
      "data": {
        "file_path": "downloads/...",
        "filename": "video.mp4"
      }
    }
  }
  ```

### Download File
- **GET** `/files/:taskId`
- Success returns binary file stream.

## 4. Security Headers

Optional VIP bypass:
```http
X-App-Secret: <APP_SECRET_KEY>
```

Conditional App Check (for non-VIP only when enabled on server):
```http
X-Firebase-AppCheck: <valid_token>
```

## 5. Handling `429` Errors

If you hit `429 TOO_MANY_REQUESTS`:
1. Wait for cooldown/ban expiry.
2. Reduce request frequency.
3. Use VIP header only for trusted clients.
