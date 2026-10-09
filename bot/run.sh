#!/bin/sh
# Script runner untuk Linux/VPS
while true; do
    echo "[$(date)] Menjalankan bot Finch..."
    python main.py
    echo "[$(date)] Bot berhenti/crash. Restart dalam 5 detik..."
    sleep 5
done