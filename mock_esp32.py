from flask import Flask, request, jsonify

# ============================================================
# ECOBIN ESP32 HARDWARE SIMULATOR
# Simulates the ESP32 microcontroller and servo motor
# ============================================================

app = Flask(__name__)

servo_position = "IDLE (CENTER)"
bin_status = {
    "biodegradable": "OK",
    "recyclable": "OK",
    "residual": "OK"
}


@app.route("/", methods=["GET"])
def home():
    """Health check / root endpoint matching ESP32."""
    print("[ESP32 SIMULATOR] Ping received -> HTTP 200 OK")
    return "EcoBin ESP32 Controller Ready", 200


@app.route("/status", methods=["GET"])
def status():
    """Returns simulated hardware status."""
    return jsonify({
        "device": "ESP32-WROOM-32",
        "online": True,
        "servo": servo_position,
        "bins": bin_status
    }), 200


@app.route("/classify", methods=["GET"])
def classify():
    """Simulates receiving a waste classification and rotating servo."""
    global servo_position
    waste_type = request.args.get("type", "UNKNOWN").upper()

    print()
    print("=" * 50)
    print(f"🤖 [ESP32 SIMULATOR] RECEIVED COMMAND: {waste_type}")

    if waste_type == "BIODEGRADABLE":
        servo_position = "LEFT (45° - Biodegradable)"
    elif waste_type == "RECYCLABLE":
        servo_position = "CENTER (90° - Recyclable)"
    elif waste_type == "RESIDUAL":
        servo_position = "RIGHT (135° - Residual)"
    else:
        print(f"⚠️ Unknown command: {waste_type}")
        return f"Unknown waste type: {waste_type}", 400

    print(f"⚙️  [ESP32 SIMULATOR] Servo Rotated to: {servo_position}")
    print("=" * 50)
    print()

    return f"Servo moved to {waste_type}", 200


if __name__ == "__main__":
    print()
    print("=" * 60)
    print("        ECOBIN ESP32 HARDWARE SIMULATOR RUNNING")
    print("=" * 60)
    print("Simulated ESP32 listening on: http://127.0.0.1:8080")
    print("=" * 60)
    print()
    app.run(host="127.0.0.1", port=8080, debug=False)
