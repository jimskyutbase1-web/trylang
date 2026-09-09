from pathlib import Path
import os

import requests
import time

from env_loader import load_env_file

# =====================================================
# ESP32 CONNECTION
# =====================================================

BASE_DIR = Path(__file__).resolve().parent
load_env_file(BASE_DIR / ".env")

ESP32_IP = os.getenv("ESP32_IP", "192.168.8.112").strip()

ESP32_URL = f"http://{ESP32_IP}"


# =====================================================
# CHECK ESP32 CONNECTION
# =====================================================

def check_connection():

    try:

        response = requests.get(
            f"{ESP32_URL}/status",
            timeout=5
        )

        if response.status_code == 200:

            print("ESP32 connected!")

            print(response.json())

            return True

        else:

            print(
                "ESP32 returned:",
                response.status_code
            )

            return False

    except requests.exceptions.RequestException as e:

        print("Cannot connect to ESP32.")

        print(e)

        return False


# =====================================================
# GET BIN STATUS
# =====================================================

def get_bin_status():

    try:

        response = requests.get(
            f"{ESP32_URL}/status",
            timeout=5
        )

        if response.status_code == 200:

            data = response.json()

            return data

        else:

            print(
                "Status error:",
                response.status_code
            )

            return None

    except requests.exceptions.RequestException as e:

        print("Connection error:")

        print(e)

        return None


# =====================================================
# SEND CLASSIFICATION TO ESP32
# =====================================================

def send_classification(waste_type):

    waste_type = waste_type.upper()

    allowed_types = [
        "BIODEGRADABLE",
        "RECYCLABLE",
        "RESIDUAL"
    ]

    if waste_type not in allowed_types:

        print(
            "Invalid waste type:",
            waste_type
        )

        return False

    try:

        response = requests.get(
            f"{ESP32_URL}/classify",
            params={
                "type": waste_type
            },
            timeout=10
        )

        print(
            "ESP32 response:",
            response.text
        )

        if response.status_code == 200:

            print(
                f"{waste_type} sent successfully."
            )

            return True

        elif response.status_code == 409:

            print(
                f"{waste_type} bin is FULL."
            )

            return False

        else:

            print(
                "ESP32 error:",
                response.status_code
            )

            return False

    except requests.exceptions.RequestException as e:

        print("Failed to send classification.")

        print(e)

        return False


# =====================================================
# PRINT BIN STATUS
# =====================================================

def print_bin_status():

    data = get_bin_status()

    if data is None:

        return

    print()
    print("==============================")
    print("ECOBIN STATUS")
    print("==============================")

    print(
        "Biodegradable:",
        data["biodegradable"],
        "%"
    )

    print(
        "Status:",
        data["status1"]
    )

    print()

    print(
        "Recyclable:",
        data["recyclable"],
        "%"
    )

    print(
        "Status:",
        data["status2"]
    )

    print()

    print(
        "Residual:",
        data["residual"],
        "%"
    )

    print(
        "Status:",
        data["status3"]
    )

    print("==============================")


# =====================================================
# TEST PROGRAM
# =====================================================

if __name__ == "__main__":

    print("==============================")
    print("ECOBIN VS CODE CONNECTION")
    print("==============================")

    print()

    # Test ESP32 connection

    if check_connection():

        print()

        print_bin_status()

        print()

        print("Testing classification...")

        # Uncomment ONE at a time for servo testing

        # send_classification("BIODEGRADABLE")

        # send_classification("RECYCLABLE")

        # send_classification("RESIDUAL")

    else:

        print()
        print("ESP32 is not reachable.")
