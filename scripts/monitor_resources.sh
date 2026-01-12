#!/bin/bash
# Real-time Docker Resource Monitor
# Updates values in-place without scrolling
#
# Usage: ./scripts/monitor_resources.sh [interval_seconds]
# Press Ctrl+C to stop

INTERVAL=${1:-2}

# Hide cursor and cleanup on exit
tput civis
trap 'tput cnorm; echo ""; exit 0' SIGINT SIGTERM

# Clear screen once at start
clear

# Draw static frame once (rows 0-19)
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Media Downloader Monitor    Time:                       ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  📊 CONTAINERS                                           ║"
echo "║  ────────────────────────────────────────────────────    ║"
echo "║  Worker:   CPU:          MEM:                            ║"
echo "║  API:      CPU:          MEM:                            ║"
echo "║  Redis:    CPU:          MEM:                            ║"
echo "║  Nginx:    CPU:          MEM:                            ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  💾 DISK                                                 ║"
echo "║  Downloads:                                              ║"
echo "║  System:                                                 ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  🔴 REDIS             👷 WORKER                          ║"
echo "║  Memory:              Active:                            ║"
echo "║  Keys:                Reserved:                          ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  Refresh: ${INTERVAL}s | Ctrl+C to stop                            ║"
echo "╚══════════════════════════════════════════════════════════╝"

# Update loop - only update values, not the frame
while true; do
    # Time (row 1, col 38)
    tput cup 1 38
    printf "%-16s" "$(date '+%H:%M:%S')"
    
    # Get docker stats
    STATS=$(docker stats --no-stream --format "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}" 2>/dev/null)
    
    # Worker stats (row 5)
    W_CPU=$(echo "$STATS" | grep "worker" | cut -d'|' -f2 | head -1)
    W_MEM=$(echo "$STATS" | grep "worker" | cut -d'|' -f3 | head -1)
    tput cup 5 17
    printf "%-12s" "${W_CPU:-N/A}"
    tput cup 5 34
    printf "%-22s" "${W_MEM:-N/A}"
    
    # API stats (row 6)
    A_CPU=$(echo "$STATS" | grep "_api" | cut -d'|' -f2 | head -1)
    A_MEM=$(echo "$STATS" | grep "_api" | cut -d'|' -f3 | head -1)
    tput cup 6 17
    printf "%-12s" "${A_CPU:-N/A}"
    tput cup 6 34
    printf "%-22s" "${A_MEM:-N/A}"
    
    # Redis stats (row 7)
    R_CPU=$(echo "$STATS" | grep "redis" | cut -d'|' -f2 | head -1)
    R_MEM=$(echo "$STATS" | grep "redis" | cut -d'|' -f3 | head -1)
    tput cup 7 17
    printf "%-12s" "${R_CPU:-N/A}"
    tput cup 7 34
    printf "%-22s" "${R_MEM:-N/A}"
    
    # Nginx stats (row 8)
    N_CPU=$(echo "$STATS" | grep "nginx" | cut -d'|' -f2 | head -1)
    N_MEM=$(echo "$STATS" | grep "nginx" | cut -d'|' -f3 | head -1)
    tput cup 8 17
    printf "%-12s" "${N_CPU:-N/A}"
    tput cup 8 34
    printf "%-22s" "${N_MEM:-N/A}"
    
    # Downloads folder (row 11)
    if [ -d "./downloads" ]; then
        DL_SIZE=$(du -sh ./downloads 2>/dev/null | cut -f1)
        DL_FILES=$(find ./downloads -type f 2>/dev/null | wc -l)
        tput cup 11 15
        printf "%-40s" "${DL_SIZE} (${DL_FILES} files)"
    fi
    
    # System disk (row 12)
    DISK_INFO=$(df -h . 2>/dev/null | tail -1 | awk '{print $3 " / " $2 " (" $5 ")"}')
    tput cup 12 12
    printf "%-40s" "$DISK_INFO"
    
    # Redis memory (row 15)
    REDIS_MEM=$(docker exec downloader_redis redis-cli INFO memory 2>/dev/null | grep "used_memory_human" | cut -d: -f2 | tr -d '\r' || echo "N/A")
    tput cup 15 12
    printf "%-12s" "$REDIS_MEM"
    
    # Redis keys (row 16)
    REDIS_KEYS=$(docker exec downloader_redis redis-cli DBSIZE 2>/dev/null | grep -oP '\d+' || echo "0")
    tput cup 16 9
    printf "%-12s" "$REDIS_KEYS"
    
    # Worker active (row 15, col 43)
    ACTIVE=$(docker exec downloader_worker celery -A app.tasks inspect active --json 2>/dev/null | grep -o '"id"' | wc -l || echo "0")
    tput cup 15 43
    printf "%-10s" "$ACTIVE"
    
    # Worker reserved (row 16, col 43)
    RESERVED=$(docker exec downloader_worker celery -A app.tasks inspect reserved --json 2>/dev/null | grep -o '"id"' | wc -l || echo "0")
    tput cup 16 43
    printf "%-10s" "$RESERVED"
    
    sleep $INTERVAL
done
