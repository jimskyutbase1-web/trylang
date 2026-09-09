# EcoBin

EcoBin classifies waste from a laptop camera and sends the selected bin command to an ESP32 over the local network. The ESP32 controls the servo lids and reports bin fill levels through Blynk.

## Requirements

- Python 3.12
- An ESP32 connected to the same local Wi-Fi network as the laptop
- ESP32 firmware that exposes `GET /classify?type=...` and `GET /status`
- The trained `waste_classifier.keras` model and `class_names.json` in the project root

## Setup

Create and activate a virtual environment, then install the dependencies:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Set `ESP32_IP` in `ecobin_server.py` to the address printed by the ESP32 Serial Monitor. The laptop and ESP32 must be on the same non-guest Wi-Fi network with client/AP isolation disabled.

## Run

Start the Flask AI server in one terminal:

```powershell
python ecobin_server.py
```

Then start the camera client in another terminal:

```powershell
python camera_ecobin.py
```

You can verify ESP32 connectivity without moving a servo by opening:

```text
http://<ESP32_IP>/status
```

## Security

Do not commit Wi-Fi passwords, Blynk tokens, or other device secrets. Keep ESP32 credentials in a local `secrets.h` file, which is ignored by Git.
