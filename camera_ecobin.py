from pathlib import Path
import time
import cv2
import requests


# ============================================================
# ECOBIN CAMERA CLIENT
# Laptop Camera -> Flask AI Server -> ESP32 -> Servo
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

# ============================================================
# FLASK SERVER
# ============================================================

SERVER_URL = "http://127.0.0.1:5000"
CLASSIFY_URL = f"{SERVER_URL}/classify"


# ============================================================
# CAMERA SETTINGS
# ============================================================

CAMERA_INDEX = 0

# Send one image every 1 second.
# This prevents the ESP32 from receiving commands too quickly.
SEND_INTERVAL = 1.0

# IMPORTANT:
# This must match ecobin_server.py
MIN_CONFIDENCE = 0.80


# ============================================================
# OPEN CAMERA
# ============================================================

camera = cv2.VideoCapture(CAMERA_INDEX)

if not camera.isOpened():

    raise RuntimeError(
        "Could not open the laptop camera. "
        "Try CAMERA_INDEX = 1 if another camera is available."
    )


camera.set(
    cv2.CAP_PROP_FRAME_WIDTH,
    640
)

camera.set(
    cv2.CAP_PROP_FRAME_HEIGHT,
    480
)


# ============================================================
# START MESSAGE
# ============================================================

print()
print("=" * 60)
print("              ECOBIN CAMERA CLIENT")
print("=" * 60)

print("Camera: READY")
print("Flask server:", CLASSIFY_URL)
print("Minimum confidence:", MIN_CONFIDENCE * 100, "%")
print("Send interval:", SEND_INTERVAL, "second")
print()
print("Flow:")
print("Camera -> Flask AI -> ESP32 -> Servo")
print()
print("Press Q to quit.")
print()


# ============================================================
# VARIABLES
# ============================================================

last_send = 0

last_class = "-"
last_confidence = 0.0

last_message = "Waiting for AI..."

last_command_status = "NOT SENT"


# ============================================================
# MAIN CAMERA LOOP
# ============================================================

while True:

    success, frame = camera.read()

    if not success:

        print(
            "Could not read frame from camera."
        )

        break


    now = time.time()


    # ========================================================
    # SEND IMAGE TO FLASK
    # ========================================================

    if now - last_send >= SEND_INTERVAL:

        last_send = now

        try:

            # ------------------------------------------------
            # Encode camera image as JPEG
            # ------------------------------------------------

            ok, encoded = cv2.imencode(
                ".jpg",
                frame,
                [
                    cv2.IMWRITE_JPEG_QUALITY,
                    85
                ]
            )


            if not ok:

                last_message = (
                    "Could not encode image"
                )

                last_command_status = (
                    "NOT SENT"
                )

            else:

                # --------------------------------------------
                # Prepare image for Flask
                # --------------------------------------------

                files = {

                    "image": (
                        "camera.jpg",
                        encoded.tobytes(),
                        "image/jpeg"
                    )

                }


                # --------------------------------------------
                # Send image to Flask
                # --------------------------------------------

                response = requests.post(

                    CLASSIFY_URL,

                    files=files,

                    timeout=5

                )


                # =================================================
                # FLASK RESPONSE
                # =================================================

                if response.status_code == 200:

                    data = response.json()


                    # ---------------------------------------------
                    # Get AI result
                    # ---------------------------------------------

                    last_class = str(
                        data.get(
                            "class",
                            "-"
                        )
                    )


                    last_confidence = float(
                        data.get(
                            "confidence",
                            0.0
                        )
                    )


                    accepted = bool(
                        data.get(
                            "accepted",
                            False
                        )
                    )


                    command_sent = bool(
                        data.get(
                            "command_sent",
                            False
                        )
                    )


                    last_message = str(
                        data.get(
                            "message",
                            "OK"
                        )
                    )


                    # =================================================
                    # SHOW RESULT
                    # =================================================

                    print(
                        f"AI: "
                        f"{last_class.upper()} "
                        f"{last_confidence * 100:.1f}%"
                    )


                    # =================================================
                    # COMMAND SENT
                    # =================================================

                    if command_sent:

                        last_command_status = (
                            "COMMAND SENT"
                        )

                        print(
                            "   -> ESP32: COMMAND SENT"
                        )

                        print(
                            f"   -> Waste type: "
                            f"{last_class.upper()}"
                        )

                        print(
                            f"   -> Server: "
                            f"{last_message}"
                        )


                    # =================================================
                    # ACCEPTED BUT NOT SENT
                    # =================================================

                    elif accepted:

                        last_command_status = (
                            "NOT SENT"
                        )

                        print(
                            "   -> AI accepted, "
                            "but command was NOT sent"
                        )

                        print(
                            f"   -> Server: "
                            f"{last_message}"
                        )


                    # =================================================
                    # BELOW CONFIDENCE
                    # =================================================

                    else:

                        last_command_status = (
                            "NOT SENT"
                        )

                        print(
                            "   -> NOT SENT"
                        )

                        print(
                            f"   -> Confidence below "
                            f"{MIN_CONFIDENCE * 100:.0f}%"
                        )


                    print()


                # =================================================
                # FLASK ERROR
                # =================================================

                else:

                    last_message = (
                        f"Flask HTTP "
                        f"{response.status_code}"
                    )

                    last_command_status = (
                        "SERVER ERROR"
                    )

                    print()
                    print(
                        "FLASK SERVER ERROR"
                    )

                    print(
                        "HTTP status:",
                        response.status_code
                    )

                    print(
                        "Response:",
                        response.text
                    )

                    print()


        # ========================================================
        # CONNECTION ERROR
        # ========================================================

        except requests.exceptions.ConnectionError:

            last_message = (
                "Flask server OFFLINE"
            )

            last_command_status = (
                "SERVER OFFLINE"
            )

            print(
                "ERROR: Flask server is offline."
            )


        # ========================================================
        # TIMEOUT
        # ========================================================

        except requests.exceptions.Timeout:

            last_message = (
                "Flask server TIMEOUT"
            )

            last_command_status = (
                "TIMEOUT"
            )

            print(
                "ERROR: Flask server timeout."
            )


        # ========================================================
        # OTHER ERROR
        # ========================================================

        except Exception as e:

            last_message = (
                f"Error: {e}"
            )

            last_command_status = (
                "ERROR"
            )

            print(
                "ERROR:",
                e
            )


    # ============================================================
    # CAMERA DISPLAY
    # ============================================================

    title = (
        f"{last_class.upper()} "
        f"{last_confidence * 100:.1f}%"
    )


    # AI prediction
    cv2.putText(

        frame,

        title,

        (20, 40),

        cv2.FONT_HERSHEY_SIMPLEX,

        0.9,

        (0, 255, 0),

        2

    )


    # Server message
    cv2.putText(

        frame,

        f"Server: {last_message}",

        (20, 80),

        cv2.FONT_HERSHEY_SIMPLEX,

        0.55,

        (255, 255, 255),

        2

    )


    # Command status
    cv2.putText(

        frame,

        f"ESP32: {last_command_status}",

        (20, 115),

        cv2.FONT_HERSHEY_SIMPLEX,

        0.65,

        (0, 255, 255),

        2

    )


    # System flow
    cv2.putText(

        frame,

        "Camera -> Flask -> ESP32 -> Servo",

        (20, 150),

        cv2.FONT_HERSHEY_SIMPLEX,

        0.55,

        (255, 255, 255),

        2

    )


    # Quit instruction
    cv2.putText(

        frame,

        "Q = Quit",

        (20, 460),

        cv2.FONT_HERSHEY_SIMPLEX,

        0.6,

        (255, 255, 255),

        2

    )


    # Show camera
    cv2.imshow(

        "ECOBIN - Live Waste Classification",

        frame

    )


    # ============================================================
    # QUIT
    # ============================================================

    if cv2.waitKey(1) & 0xFF == ord("q"):

        break


# ============================================================
# CLEANUP
# ============================================================

camera.release()

cv2.destroyAllWindows()


print()
print("=" * 60)
print("          ECOBIN CAMERA STOPPED")
print("=" * 60)