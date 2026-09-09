import os
import time
import threading
import requests

# Load Firebase URL from environment or .env
FIREBASE_URL = os.getenv("FIREBASE_DB_URL", "").strip().rstrip("/")
ESP32_IP = os.getenv("ESP32_IP", "192.168.8.112").strip()


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

    # Run in daemon thread so local ESP32 servo response is instantaneous
    t = threading.Thread(target=_push_worker, args=(payload,), daemon=True)
    t.start()
