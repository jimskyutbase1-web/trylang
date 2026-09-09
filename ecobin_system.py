"""
ECOBIN ALL-IN-ONE PYTHON SYSTEM
--------------------------------
This single Python file combines:
1. AI model training
2. Flask AI/API server
3. Laptop camera client

Normal use:
    python ecobin_system.py
    -> starts Flask server + laptop camera

Other modes:
    python ecobin_system.py train
    python ecobin_system.py server
    python ecobin_system.py camera

Required files/folders:
    dataset/
        biodegradable/
        recyclable/
        residual/

The trained model is:
    waste_classifier.keras

ESP32 is still programmed separately with Arduino IDE.
The ESP32 communicates with this Python program over Wi-Fi/HTTP.
"""

import os
import sys
import time
import threading
from pathlib import Path

import cv2
import numpy as np
import requests
import tensorflow as tf
from flask import Flask, request, jsonify
from flask_cors import CORS
from tensorflow import keras
from tensorflow.keras import layers
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input


# ============================================================
# PROJECT SETTINGS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATASET_DIR = BASE_DIR / "dataset"
MODEL_PATH = BASE_DIR / "waste_classifier.keras"

CLASS_NAMES = [
    "biodegradable",
    "recyclable",
    "residual"
]

IMG_SIZE = (224, 224)
BATCH_SIZE = 16
SEED = 123

CONFIDENCE_THRESHOLD = 0.90

CAMERA_INDEX = 0
SEND_INTERVAL = 0.20

BIN_CODE = "BIN-001"

# ============================================================
# FLASK SERVER
# ============================================================

app = Flask(__name__)
CORS(app)

model = None
pending_command = None
command_id = 0
last_sensor_data = {
    "bin_code": BIN_CODE,
    "biodegradable": {},
    "recyclable": {},
    "residual": {},
    "tof_distance_mm": -1
}
last_ack = None


# ============================================================
# MODEL LOADING
# ============================================================

def load_ai_model():
    global model

    print("Loading AI model...")
    print("Model path:", MODEL_PATH)

    if not MODEL_PATH.exists():
        print("ERROR: waste_classifier.keras was not found.")
        print("Run:")
        print("    python ecobin_system.py train")
        return False

    try:
        model = tf.keras.models.load_model(MODEL_PATH)
        print("AI model loaded successfully.")
        print("Classes:", CLASS_NAMES)
        return True
    except Exception as e:
        print("ERROR loading AI model:", e)
        model = None
        return False


# ============================================================
# AI CLASSIFICATION
# ============================================================

def classify_image(frame):
    if model is None:
        return None, 0.0

    try:
        image = cv2.resize(frame, IMG_SIZE)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        image = image.astype(np.float32)

        image = preprocess_input(image)
        image = np.expand_dims(image, axis=0)

        prediction = model.predict(image, verbose=0)[0]

        class_index = int(np.argmax(prediction))
        confidence = float(prediction[class_index])
        class_name = CLASS_NAMES[class_index]

        return class_name, confidence

    except Exception as e:
        print("AI ERROR:", e)
        return None, 0.0


# ============================================================
# AI -> ESP32 COMMAND
# ============================================================

def send_to_compartment(class_name):
    global pending_command
    global command_id

    # IMPORTANT:
    # Use "recyclable", not "non_biodegradable".
    # The ESP32 firmware should use the same compartment name.
    mapping = {
        "biodegradable": "biodegradable",
        "recyclable": "recyclable",
        "residual": "residual"
    }

    if class_name not in mapping:
        print("Unknown AI class:", class_name)
        return False

    # Do not overwrite an existing command waiting for ESP32.
    if pending_command is not None:
        print("A previous ESP32 command is still pending.")
        return False

    compartment = mapping[class_name]
    command_id += 1

    pending_command = {
        "id": command_id,
        "compartment_key": compartment,
        "command": "OPEN"
    }

    print()
    print("=" * 60)
    print("ESP32 COMMAND CREATED")
    print("=" * 60)
    print("AI CLASS:", class_name)
    print("COMPARTMENT:", compartment)
    print("COMMAND: OPEN")
    print("COMMAND ID:", command_id)
    print("=" * 60)
    print()

    return True


# ============================================================
# ESP32 SENSOR DATA API
# ============================================================

@app.route("/api/esp32_data.php", methods=["POST"])
def esp32_data():
    global last_sensor_data

    try:
        data = request.get_json()

        if not data:
            return jsonify({
                "success": False,
                "message": "No JSON received"
            }), 400

        received_bin = data.get("bin_code")

        if received_bin != BIN_CODE:
            print("WARNING: Unknown BIN CODE:", received_bin)

        last_sensor_data = data

        print()
        print("========== ESP32 SENSOR DATA ==========")
        print(data)
        print("=======================================")
        print()

        return jsonify({
            "success": True,
            "message": "Sensor data received"
        }), 200

    except Exception as e:
        print("ESP32 DATA ERROR:", e)

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# ============================================================
# ESP32 COMMAND API
# ============================================================

@app.route("/api/esp32_command.php", methods=["GET"])
def esp32_command():
    bin_code = request.args.get("bin_code")

    if bin_code != BIN_CODE:
        return jsonify({
            "command": None
        }), 200

    if pending_command is None:
        return jsonify({
            "command": None
        }), 200

    print("ESP32 requested command:", pending_command)

    return jsonify(pending_command), 200


# ============================================================
# ESP32 ACK API
# ============================================================

@app.route("/api/esp32_command_ack.php", methods=["GET"])
def esp32_command_ack():
    global pending_command
    global last_ack

    command_id_received = request.args.get("id")
    status = request.args.get("status")

    last_ack = {
        "id": command_id_received,
        "status": status,
        "time": time.time()
    }

    print()
    print("========== ESP32 COMMAND ACK ==========")
    print("Command ID:", command_id_received)
    print("Status:", status)
    print("========================================")
    print()

    if pending_command is not None:
        try:
            if int(command_id_received) == pending_command["id"]:
                pending_command = None
                print("Command removed from queue.")
        except Exception:
            pass

    return jsonify({
        "success": True,
        "message": "Command acknowledged"
    }), 200


# ============================================================
# AI CLASSIFICATION API
# ============================================================

@app.route("/classify", methods=["POST"])
def classify_api():
    try:
        if "image" not in request.files:
            return jsonify({
                "success": False,
                "message": "No image received"
            }), 400

        image_file = request.files["image"]
        image_bytes = image_file.read()

        image_array = np.frombuffer(
            image_bytes,
            np.uint8
        )

        frame = cv2.imdecode(
            image_array,
            cv2.IMREAD_COLOR
        )

        if frame is None:
            return jsonify({
                "success": False,
                "message": "Invalid image"
            }), 400

        class_name, confidence = classify_image(frame)

        if class_name is None:
            return jsonify({
                "success": False,
                "message": "AI classification failed"
            }), 500

        print(
            f"AI: {class_name.upper()} "
            f"{confidence * 100:.2f}%"
        )

        if confidence < CONFIDENCE_THRESHOLD:
            print("LOW CONFIDENCE - no servo command.")

            return jsonify({
                "success": True,
                "accepted": False,
                "class": class_name,
                "confidence": confidence,
                "message": "Confidence below threshold"
            }), 200

        command_created = send_to_compartment(class_name)

        if command_created:
            message = "Command queued for ESP32"
        else:
            message = "Command not queued; previous command may still be pending"

        return jsonify({
            "success": command_created,
            "accepted": True,
            "class": class_name,
            "confidence": confidence,
            "message": message
        }), 200

    except Exception as e:
        print("CLASSIFICATION ERROR:", e)

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# ============================================================
# STATUS API
# ============================================================

@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "system": "ECOBIN",
        "server": "online",
        "bin_code": BIN_CODE,
        "ai_model": model is not None,
        "model_file": str(MODEL_PATH),
        "pending_command": pending_command,
        "last_sensor_data": last_sensor_data,
        "last_ack": last_ack
    })


# ============================================================
# HOME PAGE
# ============================================================

@app.route("/", methods=["GET"])
def home():
    return """
    <html>
    <head>
        <title>EcoBin AI System</title>
    </head>
    <body>
        <h1>ECOBIN AI SYSTEM</h1>

        <h2>System Status</h2>
        <p>Flask server is running.</p>

        <h2>Waste Categories</h2>
        <ul>
            <li>Biodegradable</li>
            <li>Recyclable</li>
            <li>Residual</li>
        </ul>

        <h2>API Test</h2>
        <p><a href="/status">Open /status</a></p>
    </body>
    </html>
    """


# ============================================================
# RUN FLASK SERVER
# ============================================================

def run_server():
    if model is None:
        load_ai_model()

    print()
    print("=" * 60)
    print("ECOBIN FLASK SERVER")
    print("=" * 60)
    print("Laptop:", "http://127.0.0.1:5000")
    print("ESP32:  http://YOUR-LAPTOP-IP:5000")
    print("=" * 60)
    print()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False
    )


# ============================================================
# LAPTOP CAMERA CLIENT
# ============================================================

def run_camera():
    server_url = "http://127.0.0.1:5000"
    classify_url = f"{server_url}/classify"

    camera = cv2.VideoCapture(CAMERA_INDEX)

    if not camera.isOpened():
        raise RuntimeError(
            "Could not open the laptop camera. "
            "Try CAMERA_INDEX = 1 if another camera is available."
        )

    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    print()
    print("=" * 60)
    print("ECOBIN CAMERA CLIENT")
    print("=" * 60)
    print("Camera: READY")
    print("AI Server:", classify_url)
    print("Press Q to quit.")
    print("=" * 60)
    print()

    last_send = 0
    last_class = "-"
    last_confidence = 0.0
    last_message = "Waiting for AI..."

    try:
        while True:
            success, frame = camera.read()

            if not success:
                print("Could not read frame from camera.")
                break

            now = time.time()

            if now - last_send >= SEND_INTERVAL:
                last_send = now

                try:
                    ok, encoded = cv2.imencode(
                        ".jpg",
                        frame,
                        [cv2.IMWRITE_JPEG_QUALITY, 85]
                    )

                    if not ok:
                        last_message = "Could not encode image"
                    else:
                        files = {
                            "image": (
                                "camera.jpg",
                                encoded.tobytes(),
                                "image/jpeg"
                            )
                        }

                        response = requests.post(
                            classify_url,
                            files=files,
                            timeout=5
                        )

                        if response.status_code == 200:
                            data = response.json()

                            last_class = str(
                                data.get("class", "-")
                            )

                            last_confidence = float(
                                data.get("confidence", 0.0)
                            )

                            accepted = bool(
                                data.get("accepted", False)
                            )

                            last_message = str(
                                data.get("message", "OK")
                            )

                            if accepted and last_confidence >= CONFIDENCE_THRESHOLD:
                                print(
                                    f"AI: {last_class.upper()} "
                                    f"{last_confidence * 100:.1f}%"
                                )
                        else:
                            last_message = (
                                f"Server HTTP "
                                f"{response.status_code}"
                            )

                except requests.exceptions.ConnectionError:
                    last_message = "Flask server OFFLINE"

                except requests.exceptions.Timeout:
                    last_message = "Flask server TIMEOUT"

                except Exception as e:
                    last_message = f"Error: {e}"

            title = (
                f"{last_class.upper()} "
                f"{last_confidence * 100:.1f}%"
            )

            cv2.putText(
                frame,
                title,
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (0, 255, 0),
                2
            )

            cv2.putText(
                frame,
                f"Server: {last_message}",
                (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                2
            )

            cv2.putText(
                frame,
                "Camera -> AI -> ESP32 -> Servo",
                (20, 115),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                2
            )

            cv2.putText(
                frame,
                "Q = Quit",
                (20, 460),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2
            )

            cv2.imshow(
                "ECOBIN - Live Waste Classification",
                frame
            )

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    finally:
        camera.release()
        cv2.destroyAllWindows()

        print()
        print("=" * 60)
        print("ECOBIN CAMERA STOPPED")
        print("=" * 60)


# ============================================================
# TRAINING
# ============================================================

def train_model():
    print("=" * 60)
    print("ECOBIN AI MODEL TRAINING")
    print("=" * 60)

    print("TensorFlow:", tf.__version__)

    if not DATASET_DIR.exists():
        raise FileNotFoundError(
            f"Dataset folder not found: {DATASET_DIR}"
        )

    # Count images dynamically.
    class_counts = {}

    print("\nDataset:")

    for index, class_name in enumerate(CLASS_NAMES):
        folder = DATASET_DIR / class_name

        if not folder.is_dir():
            raise FileNotFoundError(
                f"Missing folder: {folder}"
            )

        count = sum(
            1 for f in folder.iterdir()
            if f.is_file()
        )

        class_counts[index] = count

        print(f"  {class_name}: {count}")

    print("\nLoading training data...")

    train_dataset = tf.keras.utils.image_dataset_from_directory(
        str(DATASET_DIR),
        labels="inferred",
        label_mode="int",
        class_names=CLASS_NAMES,
        validation_split=0.20,
        subset="training",
        seed=SEED,
        image_size=IMG_SIZE,
        batch_size=BATCH_SIZE,
        shuffle=True
    )

    print("Loading validation data...")

    validation_dataset = tf.keras.utils.image_dataset_from_directory(
        str(DATASET_DIR),
        labels="inferred",
        label_mode="int",
        class_names=CLASS_NAMES,
        validation_split=0.20,
        subset="validation",
        seed=SEED,
        image_size=IMG_SIZE,
        batch_size=BATCH_SIZE,
        shuffle=False
    )

    autotune = tf.data.AUTOTUNE

    train_dataset = train_dataset.prefetch(autotune)
    validation_dataset = validation_dataset.prefetch(autotune)

    # Data augmentation helps the smaller classes.
    data_augmentation = keras.Sequential(
        [
            layers.RandomFlip("horizontal"),
            layers.RandomRotation(0.10),
            layers.RandomZoom(0.15),
            layers.RandomContrast(0.10),
        ],
        name="data_augmentation"
    )

    # Dynamic class weights.
    total = sum(class_counts.values())
    number_of_classes = len(CLASS_NAMES)

    class_weights = {}

    for class_index, count in class_counts.items():
        class_weights[class_index] = (
            total / (number_of_classes * count)
        )

    print("\nClass weights:")

    for index, weight in class_weights.items():
        print(
            f"  {CLASS_NAMES[index]}: {weight:.3f}"
        )

    print("\nCreating MobileNetV2...")

    base_model = MobileNetV2(
        input_shape=(224, 224, 3),
        include_top=False,
        weights="imagenet"
    )

    base_model.trainable = False

    inputs = keras.Input(
        shape=(224, 224, 3),
        name="image"
    )

    x = data_augmentation(inputs)
    x = preprocess_input(x)

    x = base_model(
        x,
        training=False
    )

    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dropout(0.30)(x)

    outputs = layers.Dense(
        3,
        activation="softmax",
        name="waste_class"
    )(x)

    training_model = keras.Model(
        inputs,
        outputs,
        name="EcoBin_Waste_Classifier"
    )

    training_model.compile(
        optimizer=keras.optimizers.Adam(
            learning_rate=0.0001
        ),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"]
    )

    callbacks = [
        keras.callbacks.ModelCheckpoint(
            str(MODEL_PATH),
            monitor="val_accuracy",
            save_best_only=True,
            verbose=1
        ),
        keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=4,
            restore_best_weights=True,
            verbose=1
        ),
        keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.3,
            patience=2,
            min_lr=1e-7,
            verbose=1
        )
    ]

    print("\n" + "=" * 60)
    print("INITIAL TRAINING")
    print("=" * 60)

    training_model.fit(
        train_dataset,
        validation_data=validation_dataset,
        epochs=15,
        class_weight=class_weights,
        callbacks=callbacks
    )

    print("\n" + "=" * 60)
    print("FINE-TUNING")
    print("=" * 60)

    base_model.trainable = True

    fine_tune_from = 100

    for layer in base_model.layers[:fine_tune_from]:
        layer.trainable = False

    training_model.compile(
        optimizer=keras.optimizers.Adam(
            learning_rate=1e-5
        ),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"]
    )

    training_model.fit(
        train_dataset,
        validation_data=validation_dataset,
        epochs=10,
        class_weight=class_weights,
        callbacks=callbacks
    )

    print("\nLoading best model...")

    best_model = keras.models.load_model(
        str(MODEL_PATH)
    )

    loss, accuracy = best_model.evaluate(
        validation_dataset,
        verbose=1
    )

    best_model.save(str(MODEL_PATH))

    print("\n" + "=" * 60)
    print("TRAINING COMPLETE")
    print("=" * 60)
    print(f"Validation accuracy: {accuracy * 100:.2f}%")
    print(f"Model saved to:")
    print(MODEL_PATH)
    print("=" * 60)


# ============================================================
# START SERVER + CAMERA
# ============================================================

def run_all():
    if not load_ai_model():
        print("\nAI model is missing.")
        print("Run this first:")
        print("    python ecobin_system.py train")
        return

    server_thread = threading.Thread(
        target=run_server,
        daemon=True
    )

    server_thread.start()

    # Give Flask a moment to start.
    time.sleep(2)

    run_camera()


# ============================================================
# MAIN MENU
# ============================================================

def main():
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "all"

    if mode == "train":
        train_model()

    elif mode == "server":
        load_ai_model()
        run_server()

    elif mode == "camera":
        run_camera()

    elif mode == "all":
        run_all()

    else:
        print("Unknown mode:", mode)
        print()
        print("Use one of:")
        print("  python ecobin_system.py")
        print("  python ecobin_system.py train")
        print("  python ecobin_system.py server")
        print("  python ecobin_system.py camera")


if __name__ == "__main__":
    main()
