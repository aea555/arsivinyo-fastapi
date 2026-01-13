#!/bin/bash
# Disk Cleanup Script for Media Downloader
# Run this periodically via cron to prevent disk from filling up
#
# Recommended cron entry (every 30 minutes):
# */30 * * * * /path/to/cleanup_downloads.sh >> /var/log/cleanup.log 2>&1

DOWNLOAD_DIR="${DOWNLOAD_DIR:-./downloads}"
MAX_AGE_MINUTES="${MAX_AGE_MINUTES:-30}"  # Delete files older than 30 minutes
MAX_DISK_USAGE_PERCENT="${MAX_DISK_USAGE_PERCENT:-80}"  # Start aggressive cleanup at 80%

echo "========================================"
echo "Cleanup started at $(date)"
echo "Download dir: $DOWNLOAD_DIR"
echo "Max age: $MAX_AGE_MINUTES minutes"
echo "========================================"

# Check if download directory exists
# Check if download directory exists, create if not
if [ ! -d "$DOWNLOAD_DIR" ]; then
    echo "Creating download directory: $DOWNLOAD_DIR"
    mkdir -p "$DOWNLOAD_DIR"
fi

# Get current disk usage
DISK_USAGE=$(df "$DOWNLOAD_DIR" | tail -1 | awk '{print $5}' | sed 's/%//')
echo "Current disk usage: ${DISK_USAGE}%"

# Count files before cleanup
FILES_BEFORE=$(find "$DOWNLOAD_DIR" -type f | wc -l)
SIZE_BEFORE=$(du -sh "$DOWNLOAD_DIR" 2>/dev/null | cut -f1)
echo "Files before cleanup: $FILES_BEFORE ($SIZE_BEFORE)"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "⚠️  Forcing root: Script must be run with sudo to delete Docker-created files."
    echo "Try: sudo $0"
    exit 1
fi

# Standard cleanup: Remove files older than MAX_AGE_MINUTES
echo ""
echo "Removing files older than $MAX_AGE_MINUTES minutes..."
find "$DOWNLOAD_DIR" -type f -mmin +$MAX_AGE_MINUTES -delete

# Aggressive cleanup if disk usage is high
if [ "$DISK_USAGE" -gt "$MAX_DISK_USAGE_PERCENT" ]; then
    echo ""
    echo "⚠️ Disk usage is high (${DISK_USAGE}%), performing aggressive cleanup..."
    
    # Remove ALL files older than 10 minutes
    find "$DOWNLOAD_DIR" -type f -mmin +10 -delete 2>/dev/null
    
    # If still high, remove everything except last 5 minutes
    DISK_USAGE_AFTER=$(df "$DOWNLOAD_DIR" | tail -1 | awk '{print $5}' | sed 's/%//')
    if [ "$DISK_USAGE_AFTER" -gt 90 ]; then
        echo "🚨 Critical disk usage, removing all files older than 5 minutes..."
        find "$DOWNLOAD_DIR" -type f -mmin +5 -delete 2>/dev/null
    fi
fi

# Remove empty directories
# Remove empty directories (but NOT the root download dir)
find "$DOWNLOAD_DIR" -mindepth 1 -type d -empty -delete 2>/dev/null

# Count files after cleanup
FILES_AFTER=$(find "$DOWNLOAD_DIR" -type f | wc -l)
SIZE_AFTER=$(du -sh "$DOWNLOAD_DIR" 2>/dev/null | cut -f1)
DISK_USAGE_FINAL=$(df "$DOWNLOAD_DIR" | tail -1 | awk '{print $5}' | sed 's/%//')

echo ""
echo "========================================"
echo "Cleanup completed at $(date)"
echo "Files: $FILES_BEFORE -> $FILES_AFTER"
echo "Size: $SIZE_BEFORE -> $SIZE_AFTER"
echo "Disk usage: ${DISK_USAGE}% -> ${DISK_USAGE_FINAL}%"
echo "========================================"
