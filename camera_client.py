import time
import cv2
import requests

SERVER_URL = "http://127.0.0.1:5000/classify"
CAMERA_INDEX = 0
SEND_INTERVAL = 0.35
JPEG_QUALITY = 90


def main():
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        raise RuntimeError("Could not open laptop camera")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    last_send = 0.0
    display_text = "Point one waste item at the camera"

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        now = time.time()
        if now - last_send >= SEND_INTERVAL:
            last_send = now
            encoded_ok, jpg = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
            )
            if encoded_ok:
                try:
                    response = requests.post(
                        SERVER_URL,
                        files={"image": ("frame.jpg", jpg.tobytes(), "image/jpeg")},
                        timeout=2.0,
                    )
                    data = response.json()
                    if data.get("ok"):
                        label = data["class"]
                        confidence = data["confidence"] * 100
                        accepted = data.get("accepted", False)
                        display_text = f"{label.upper()} {confidence:.1f}%"
                        if not accepted:
                            display_text += " - LOW CONFIDENCE"
                    else:
                        display_text = data.get("error", "Server error")
                except Exception as e:
                    display_text = f"Server connection error: {e}"

        cv2.putText(
            frame,
            display_text,
            (15, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.imshow("ECOBIN Waste Classifier - press Q to quit", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
