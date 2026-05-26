# Simple keep-alive — ping /health every 14 minutes
# Run this from anywhere to keep Render awake
import httpx
import time

URL = "https://cube-earth.onrender.com/health"

while True:
    try:
        r = httpx.get(URL, timeout=10)
        print(f"Ping: {r.status_code}")
    except Exception as e:
        print(f"Ping failed: {e}")
    time.sleep(840)  # 14 minutes
