from pathlib import Path
import os
import time
import threading
import requests
from env_loader import load_env_file

# Ensure .env is loaded
BASE_DIR = Path(__file__).resolve().parent
load_env_file(BASE_DIR / ".env")

_heartbeat_thread = None
_is_monitoring = False


def get_firebase_url():
    """Dynamically get Firebase URL from environment."""
    return os.getenv("FIREBASE_DB_URL", "https://ecobin-c080b-default-rtdb.firebaseio.com/").strip().rstrip("/")


def get_esp32_ip():
    """Dynamically get ESP32 IP from environment."""
    return os.getenv("ESP32_IP", "192.168.8.112").strip()


def _push_worker(payload):
    """Background worker to send telemetry to Firebase without slowing down servo."""
    fb_url = get_firebase_url()
    if not fb_url:
        return

    try:
        requests.put(
            f"{fb_url}/ecobin/latest.json",
            json=payload,
            timeout=3.0
        )
        requests.post(
            f"{fb_url}/ecobin/logs.json",
            json=payload,
            timeout=3.0
        )
    except Exception as e:
        print(f"[Firebase Sync] Push error: {e}")


def push_classification(label, confidence, probabilities, message="", esp32_ip=None):
    """Pushes new AI classification event to Firebase Realtime Database in background."""
    ip = esp32_ip or get_esp32_ip()
    payload = {
        "class": label.upper(),
        "confidence": float(confidence),
        "probabilities": {k: float(v) for k, v in probabilities.items()} if probabilities else {},
        "message": message,
        "esp32_ip": ip,
        "time": time.strftime("%I:%M:%S %p"),
        "timestamp": int(time.time())
    }

    t = threading.Thread(target=_push_worker, args=(payload,), daemon=True)
    t.start()


def push_esp32_status(is_online, ip=None, details=None):
    """Pushes active/offline status of ESP32 to Firebase Realtime Database."""
    fb_url = get_firebase_url()
    current_ip = ip or get_esp32_ip()
    
    if not fb_url:
        return

    status_payload = {
        "online": bool(is_online),
        "ip": current_ip,
        "last_seen": int(time.time()),
        "time": time.strftime("%I:%M:%S %p"),
        "details": details or ("Online & Responsive" if is_online else "Disconnected / Unreachable")
    }

    try:
        r = requests.put(
            f"{fb_url}/ecobin/esp32_status.json",
            json=status_payload,
            timeout=3.0
        )
        if is_online:
            print(f"[Firebase Sync] ESP32 ACTIVE ({current_ip}) -> Synced to Cloud")
    except Exception as e:
        print(f"[Firebase Sync] Status update failed: {e}")


def _heartbeat_loop():
    """Continuously pings the ESP32 every 3 seconds and broadcasts live active status."""
    global _is_monitoring
    current_ip = get_esp32_ip()
    print(f"[Heartbeat Monitor] Started polling ESP32 at {current_ip}...")

    while _is_monitoring:
        current_ip = get_esp32_ip()
        url = f"http://{current_ip}"
        try:
            res = requests.get(f"{url}/", timeout=2.0)
            if res.status_code == 200:
                push_esp32_status(True, ip=current_ip, details=f"HTTP 200 OK: {res.text.strip()[:40]}")
            else:
                push_esp32_status(False, ip=current_ip, details=f"HTTP Error {res.status_code}")
        except requests.exceptions.RequestException:
            push_esp32_status(False, ip=current_ip, details="Device Unreachable")

        time.sleep(3.0)


def start_heartbeat_monitor():
    """Starts the heartbeat monitoring thread if not already running."""
    global _heartbeat_thread, _is_monitoring
    if not _is_monitoring:
        _is_monitoring = True
        _heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
        _heartbeat_thread.start()
