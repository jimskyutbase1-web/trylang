import os
import time
import threading
import requests

# Load Firebase URL from environment or .env
FIREBASE_URL = os.getenv("FIREBASE_DB_URL", "").strip().rstrip("/")
ESP32_IP = os.getenv("ESP32_IP", "192.168.8.112").strip()

_heartbeat_thread = None
_is_monitoring = False


def _push_worker(payload):
    """Background worker to send telemetry to Firebase without slowing down servo."""
    if not FIREBASE_URL:
        return

    try:
        # Update latest state
        requests.put(
            f"{FIREBASE_URL}/ecobin/latest.json",
            json=payload,
            timeout=2.0
        )

        # Append to log history
        requests.post(
            f"{FIREBASE_URL}/ecobin/logs.json",
            json=payload,
            timeout=2.0
        )
    except Exception as e:
        print(f"[Firebase Sync] Non-blocking push error: {e}")


def push_classification(label, confidence, probabilities, message="", esp32_ip=ESP32_IP):
    """Pushes new AI classification event to Firebase Realtime Database in background."""
    payload = {
        "class": label.upper(),
        "confidence": float(confidence),
        "probabilities": {k: float(v) for k, v in probabilities.items()} if probabilities else {},
        "message": message,
        "esp32_ip": esp32_ip,
        "time": time.strftime("%I:%M:%S %p"),
        "timestamp": int(time.time())
    }

    t = threading.Thread(target=_push_worker, args=(payload,), daemon=True)
    t.start()


def push_esp32_status(is_online, ip=ESP32_IP, details=None):
    """Pushes active/offline status of ESP32 to Firebase Realtime Database."""
    if not FIREBASE_URL:
        return

    status_payload = {
        "online": bool(is_online),
        "ip": ip,
        "last_seen": int(time.time()),
        "time": time.strftime("%I:%M:%S %p"),
        "details": details or ("Online & Responsive" if is_online else "Disconnected / Unreachable")
    }

    try:
        requests.put(
            f"{FIREBASE_URL}/ecobin/esp32_status.json",
            json=status_payload,
            timeout=2.0
        )
    except Exception as e:
        print(f"[Firebase Sync] Status update failed: {e}")


def _heartbeat_loop():
    """Continuously pings the ESP32 every 3-5 seconds and broadcasts live active status."""
    global _is_monitoring
    print(f"[Heartbeat Monitor] Started background polling for ESP32 at {ESP32_IP}...")

    while _is_monitoring:
        url = f"http://{ESP32_IP}"
        try:
            res = requests.get(f"{url}/", timeout=2.5)
            if res.status_code == 200:
                push_esp32_status(True, ip=ESP32_IP, details=f"HTTP 200 OK: {res.text.strip()[:60]}")
            else:
                push_esp32_status(False, ip=ESP32_IP, details=f"HTTP Error {res.status_code}")
        except requests.exceptions.RequestException:
            push_esp32_status(False, ip=ESP32_IP, details="Connection Timed Out / Device Offline")

        time.sleep(3.5)


def start_heartbeat_monitor():
    """Starts the heartbeat monitoring thread if not already running."""
    global _heartbeat_thread, _is_monitoring
    if not _is_monitoring:
        _is_monitoring = True
        _heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
        _heartbeat_thread.start()
