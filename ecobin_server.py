from pathlib import Path
import json
import os
import time

import cv2
import numpy as np
import requests
import tensorflow as tf
from env_loader import load_env_file

try:
    from firebase_sync import push_classification, start_heartbeat_monitor
except ImportError:
    push_classification = None
    start_heartbeat_monitor = None

from flask import Flask, jsonify, request

try:
    from flask_cors import CORS
    has_cors = True
except ImportError:
    has_cors = False


# ============================================================
# ECOBIN AI SERVER
# Camera → AI Model → ESP32 → Servo
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
load_env_file(BASE_DIR / ".env")

if start_heartbeat_monitor:
    start_heartbeat_monitor()

MODEL_PATH = BASE_DIR / "waste_classifier.keras"
META_PATH = BASE_DIR / "class_names.json"


# ============================================================
# WASTE CLASSES
# ============================================================

CLASS_NAMES = [
    "biodegradable",
    "recyclable",
    "residual"
]

IMG_SIZE = 224

# Minimum AI confidence required
CONFIDENCE_THRESHOLD = 0.80


# ============================================================
# ESP32 SETTINGS
# ============================================================

ESP32_IP = os.getenv("ESP32_IP", "192.168.8.112").strip()
ESP32_URL = f"http://{ESP32_IP}"

# Prevent repeated commands too quickly
COMMAND_COOLDOWN = 3.0
last_command_time = 0.0


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)
if has_cors:
    CORS(app)


# ============================================================
# LOAD AI MODEL
# ============================================================

print()
print("=" * 60)
print("              ECOBIN AI SYSTEM")
print("=" * 60)
print()

print("Loading AI model...")

try:
    import keras
    model = keras.models.load_model(MODEL_PATH)
    print("AI model loaded successfully!")
except Exception as e1:
    try:
        model = tf.keras.models.load_model(MODEL_PATH)
        print("AI model loaded successfully!")
    except Exception as e2:
        print("ERROR: Could not load AI model.")
        print(e1)
        raise e1


# ============================================================
# LOAD CLASS NAMES
# ============================================================

if META_PATH.exists():

    try:

        meta = json.loads(
            META_PATH.read_text(
                encoding="utf-8"
            )
        )

        loaded_classes = meta.get(
            "class_names"
        )

        if (
            isinstance(loaded_classes, list)
            and len(loaded_classes) == 3
        ):

            CLASS_NAMES = loaded_classes

        print(
            "Class names:",
            CLASS_NAMES
        )

    except Exception as e:

        print(
            "WARNING: Could not read class_names.json"
        )

        print(e)


print()
print("ESP32 URL:", ESP32_URL)
print(
    "Confidence threshold:",
    f"{CONFIDENCE_THRESHOLD * 100:.0f}%"
)
print()


# ============================================================
# TEST ESP32 CONNECTION
# ============================================================

def test_esp32_connection():

    print("=" * 60)
    print("Testing connection to ESP32...")
    print("ESP32:", ESP32_URL)
    print("=" * 60)

    try:

        response = requests.get(
            f"{ESP32_URL}/",
            timeout=5
        )

        print("ESP32 connection: SUCCESS")
        print("HTTP status:", response.status_code)
        print("ESP32 response:", response.text)

        return True

    except requests.RequestException as e:

        print("ESP32 connection: FAILED")
        print("Error:", e)

        return False


# ============================================================
# IMAGE CLASSIFICATION
# ============================================================

def classify_image(jpeg_bytes):

    # Convert image bytes to NumPy array
    arr = np.frombuffer(
        jpeg_bytes,
        dtype=np.uint8
    )

    # Decode JPEG
    bgr = cv2.imdecode(
        arr,
        cv2.IMREAD_COLOR
    )

    if bgr is None:

        raise ValueError(
            "Could not decode image"
        )

    # BGR → RGB
    rgb = cv2.cvtColor(
        bgr,
        cv2.COLOR_BGR2RGB
    )

    # Resize
    rgb = cv2.resize(
        rgb,
        (IMG_SIZE, IMG_SIZE),
        interpolation=cv2.INTER_AREA
    )

    # Convert to float32
    x = rgb.astype(np.float32)

    # Add batch dimension
    x = np.expand_dims(
        x,
        axis=0
    )

    # AI prediction
    probs = model.predict(
        x,
        verbose=0
    )[0]

    # Safety check
    if len(probs) != len(CLASS_NAMES):

        raise ValueError(
            "Model output does not match "
            "the number of class names."
        )

    # Highest probability
    idx = int(
        np.argmax(probs)
    )

    label = CLASS_NAMES[idx]

    confidence = float(
        probs[idx]
    )

    probabilities = {
        CLASS_NAMES[i]: float(probs[i])
        for i in range(len(CLASS_NAMES))
    }

    return (
        label,
        confidence,
        probabilities
    )


# ============================================================
# SEND COMMAND TO ESP32
# ============================================================

def send_to_esp32(label):

    global last_command_time

    current_time = time.time()

    # --------------------------------------------------------
    # COMMAND COOLDOWN
    # --------------------------------------------------------

    elapsed = (
        current_time
        - last_command_time
    )

    if elapsed < COMMAND_COOLDOWN:

        remaining = (
            COMMAND_COOLDOWN
            - elapsed
        )

        print()
        print(
            "ESP32 command skipped."
        )

        print(
            f"Cooldown active: "
            f"{remaining:.1f} seconds remaining"
        )

        return {
            "success": False,
            "sent": False,
            "message": "Command cooldown active"
        }


    # --------------------------------------------------------
    # CONVERT LABEL
    # --------------------------------------------------------

    command = label.strip().upper()

    allowed_commands = {
        "BIODEGRADABLE",
        "RECYCLABLE",
        "RESIDUAL"
    }

    if command not in allowed_commands:

        return {
            "success": False,
            "sent": False,
            "message": (
                f"Invalid waste type: {command}"
            )
        }


    # --------------------------------------------------------
    # SEND TO ESP32
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("SENDING COMMAND TO ESP32")
    print("=" * 60)

    print(
        "ESP32 URL:",
        ESP32_URL
    )

    print(
        "Waste type:",
        command
    )

    try:

        response = requests.get(
            f"{ESP32_URL}/classify",
            params={
                "type": command
            },
            timeout=5
        )

        print(
            "ESP32 HTTP status:",
            response.status_code
        )

        print(
            "ESP32 response:",
            response.text
        )

        print("=" * 60)


        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

        if response.status_code == 200:

            last_command_time = current_time

            return {
                "success": True,
                "sent": True,
                "message": (
                    f"Sent {label} command "
                    "to ESP32"
                ),
                "esp32_response": response.text
            }


        # ----------------------------------------------------
        # BIN FULL
        # ----------------------------------------------------

        elif response.status_code == 409:

            return {
                "success": False,
                "sent": False,
                "message": (
                    f"{label} bin is full"
                ),
                "esp32_response": response.text
            }


        # ----------------------------------------------------
        # OTHER ERROR
        # ----------------------------------------------------

        else:

            return {
                "success": False,
                "sent": False,
                "message": (
                    f"ESP32 returned HTTP "
                    f"{response.status_code}"
                ),
                "esp32_response": response.text
            }


    except requests.Timeout:

        print()
        print("=" * 60)
        print("ESP32 REQUEST TIMEOUT")
        print("=" * 60)

        print(
            "The ESP32 did not respond within 5 seconds."
        )

        print("=" * 60)

        return {
            "success": False,
            "sent": False,
            "message": (
                "ESP32 request timed out"
            )
        }


    except requests.ConnectionError as e:

        print()
        print("=" * 60)
        print("ESP32 CONNECTION ERROR")
        print("=" * 60)

        print(
            "Could not connect to ESP32."
        )

        print(
            "Error:",
            e
        )

        print("=" * 60)

        return {
            "success": False,
            "sent": False,
            "message": (
                "Could not connect to ESP32"
            )
        }


    except requests.RequestException as e:

        print()
        print("=" * 60)
        print("ESP32 REQUEST ERROR")
        print("=" * 60)

        print(
            "Error:",
            e
        )

        print("=" * 60)

        return {
            "success": False,
            "sent": False,
            "message": (
                f"ESP32 request failed: {e}"
            )
        }


# ============================================================
# CAMERA CLASSIFICATION ENDPOINT
# ============================================================

@app.route(
    "/classify",
    methods=["POST"]
)
def classify():

    print()
    print("-" * 60)
    print("NEW CAMERA IMAGE RECEIVED")
    print("-" * 60)


    # --------------------------------------------------------
    # CHECK IMAGE
    # --------------------------------------------------------

    if "image" not in request.files:

        print(
            "ERROR: No image received."
        )

        return jsonify({
            "ok": False,
            "error": (
                "Missing multipart field: image"
            )
        }), 400


    try:

        # Read image
        image_bytes = (
            request.files["image"].read()
        )

        if not image_bytes:

            raise ValueError(
                "Received empty image"
            )


        # ----------------------------------------------------
        # AI CLASSIFICATION
        # ----------------------------------------------------

        (
            label,
            confidence,
            probabilities
        ) = classify_image(
            image_bytes
        )


    except Exception as e:

        print(
            "AI classification error:",
            e
        )

        return jsonify({
            "ok": False,
            "error": str(e)
        }), 400


    # ========================================================
    # SHOW AI RESULT
    # ========================================================

    print()
    print("AI RESULT")
    print("-" * 60)

    print(
        "Detected waste:",
        label
    )

    print(
        f"Confidence: "
        f"{confidence * 100:.2f}%"
    )

    print("Probabilities:")

    for name, probability in (
        probabilities.items()
    ):

        print(
            f"  {name}: "
            f"{probability * 100:.2f}%"
        )


    # ========================================================
    # CONFIDENCE CHECK
    # ========================================================

    accepted = (
        confidence
        >= CONFIDENCE_THRESHOLD
    )

    print()

    print(
        "Required confidence:",
        f"{CONFIDENCE_THRESHOLD * 100:.0f}%"
    )

    print(
        "Accepted:",
        accepted
    )


    # ========================================================
    # DEFAULT COMMAND RESULT
    # ========================================================

    command_result = {
        "success": False,
        "sent": False,
        "message": (
            "Prediction below confidence threshold"
        )
    }


    # ========================================================
    # SEND TO ESP32
    # ========================================================

    if accepted:

        print()
        print(
            "AI confidence accepted."
        )

        print(
            "Sending command immediately..."
        )

        command_result = send_to_esp32(
            label
        )

    else:

        print()
        print(
            "COMMAND NOT SENT"
        )

        print(
            "Reason: AI confidence is below "
            f"{CONFIDENCE_THRESHOLD * 100:.0f}%"
        )


    # ========================================================
    # FINAL RESULT
    # ========================================================

    print()
    print("-" * 60)

    if command_result["sent"]:

        print(
            "RESULT: COMMAND SENT TO ESP32"
        )

    else:

        print(
            "RESULT: COMMAND NOT SENT"
        )

    print("-" * 60)
    print()


    # ========================================================
    # RESPONSE TO CAMERA & CLOUD SYNC
    # ========================================================

    if push_classification:
        push_classification(
            label=label,
            confidence=confidence,
            probabilities=probabilities,
            message=command_result["message"],
            esp32_ip=ESP32_IP
        )

    return jsonify({

        "ok": True,

        "class": label,

        "confidence": confidence,

        "accepted": accepted,

        "command_sent": (
            command_result["sent"]
        ),

        "probabilities": probabilities,

        "message": command_result["message"],

        "esp32_response": (
            command_result.get(
                "esp32_response"
            )
        )

    })


# ============================================================
# ESP32 STATUS
# ============================================================

@app.route(
    "/esp32-status",
    methods=["GET"]
)
def esp32_status():

    try:

        response = requests.get(
            f"{ESP32_URL}/status",
            timeout=5
        )

        return jsonify({

            "python_server": True,

            "esp32_online": (
                response.status_code == 200
            ),

            "esp32_http_status": (
                response.status_code
            ),

            "esp32_response": (
                response.text
            )

        })


    except requests.Timeout:

        return jsonify({

            "python_server": True,

            "esp32_online": False,

            "error": (
                "ESP32 status request timed out"
            )

        }), 503


    except requests.RequestException as e:

        return jsonify({

            "python_server": True,

            "esp32_online": False,

            "error": str(e)

        }), 503


# ============================================================
# PYTHON SERVER STATUS
# ============================================================

@app.route(
    "/status",
    methods=["GET"]
)
def status():

    return jsonify({

        "ok": True,

        "server": "ECOBIN AI Server",

        "classes": CLASS_NAMES,

        "threshold": (
            CONFIDENCE_THRESHOLD
        ),

        "esp32_ip": ESP32_IP,

        "esp32_url": ESP32_URL,

        "cooldown": COMMAND_COOLDOWN

    })


# ============================================================
# HOME
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def home():

    return jsonify({

        "name": "ECOBIN AI Server",

        "status": "running",

        "esp32": ESP32_URL

    })


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # TEST ESP32
    # --------------------------------------------------------

    test_esp32_connection()


    # --------------------------------------------------------
    # START FLASK
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("ECOBIN AI SERVER IS READY")
    print("=" * 60)

    print()

    print(
        "Laptop server:"
    )

    print(
        "http://127.0.0.1:5000"
    )

    print()

    print(
        "Network server:"
    )

    print(
        "http://0.0.0.0:5000"
    )

    print()

    print(
        "ESP32:"
    )

    print(
        ESP32_URL
    )

    print()

    print(
        "Camera → AI → ESP32 → Servo"
    )

    print("=" * 60)
    print()


    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False
    )
