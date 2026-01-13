# Postman API Testing Guide

This guide explains how to test the Media Downloader API using Postman.

## 1. Import Collection

1. Open Postman.
2. Click **Import** (top left).
3. Drag and drop the `docs/postman_collection.json` file.
4. Or copy/paste the raw JSON content.

## 2. Configure Environment

The collection uses a variable `{{base_url}}`. You need to set this to your API URL.

**For Localhost:**
- `http://127.0.0.1:8090` (Main Nginx Port)
- `http://127.0.0.1:8000` (Direct API - Dev Bypass Only)

**For VPS:**
- `http://YOUR_VPS_IP:8090`

To edit the variable:
1. Click on the collection name **Media Downloader API**.
2. Go to the **Variables** tab.
3. Update `Current Value` for `base_url`.
4. Click **Save** (Ctrl+S).

## 3. Endpoints

### 🩺 Health Check
- **GET** `/`
- Verifies that the API is running.

### 📥 Start Download
- **POST** `/download`
- **Body:**
  ```json
  {
      "url": "https://www.youtube.com/shorts/..."
  }
  ```
- **Response:**
  ```json
  {
      "success": true,
      "data": {
          "task_id": "c123..."
      }
  }
  ```

### 🔍 Check Status
- **GET** `/status/:taskId`
- Replace `:taskId` in the URL with the ID you got from `/download`.
- **Response (Processing):**
  ```json
  {
      "status": "PROCESSING",
      "progress": 45
  }
  ```
- **Response (Success):**
  ```json
  {
      "status": "SUCCESS",
      "result": {
          "url": "https://...",
          "filename": "video.mp4"
      }
  }
  ```

## 4. Handling 429 Errors (Rate Limits)

If you see `429 Too Many Requests`:

1. **Wait:** The IP ban is temporary (usually 5 mins).
2. **Dev Bypass (Local Only):**
   - Change `base_url` to `http://127.0.0.1:8000`.
   - In the **Start Download** request headers, enable `X-App-Secret`.
   - Set value to `dev_secret_bypass` (or your secret from `.env`).
