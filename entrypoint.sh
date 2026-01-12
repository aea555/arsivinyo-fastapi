#!/bin/bash
set -e

echo "--- Starting Media Downloader Startup Script ---"

# 1. Install/Update dependencies if requirements.txt exists
if [ -f "requirements.txt" ]; then
    echo "Verifying and installing dependencies..."
    # --no-cache-dir ensures we don't bloat the container
    # --root-user-action=ignore suppresses the root user warning (expected in Docker)
    pip install --upgrade pip --root-user-action=ignore
    pip install --no-cache-dir -r requirements.txt --root-user-action=ignore
else
    echo "Warning: requirements.txt not found!"
fi

# 2. Check if we are running as API or Worker based on command
if [[ "$*" == *"uvicorn"* ]]; then
    echo "Starting FastAPI API Server..."
    exec "$@"
elif [[ "$*" == *"celery"* ]]; then
    echo "Starting Celery Worker..."
    exec "$@"
else
    echo "Executing unknown command: $*"
    exec "$@"
fi
