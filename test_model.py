from pathlib import Path
import json
import random
import numpy as np
import tensorflow as tf
from sklearn.metrics import confusion_matrix, classification_report

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "waste_classifier.keras"
MANIFEST_PATH = BASE_DIR / "test_manifest.json"
CLASS_NAMES = ["biodegradable", "recyclable", "residual"]
IMG_SIZE = 224
SEED = 123
MAX_PER_CLASS = 10

random.seed(SEED)


def load_image(path):
    raw = tf.io.read_file(path)
    image = tf.io.decode_image(raw, channels=3, expand_animations=False)
    image.set_shape([None, None, 3])
    image = tf.image.resize(image, [IMG_SIZE, IMG_SIZE])
    image = tf.cast(image, tf.float32)  # IMPORTANT: no preprocess_input here
    return image


def main():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Model not found: {MODEL_PATH}")
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"{MANIFEST_PATH.name} not found. Run train_model.py first."
        )

    print("Loading model...")
    model = tf.keras.models.load_model(MODEL_PATH)
    print("Model loaded successfully.\n")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    grouped = {name: [] for name in CLASS_NAMES}
    for item in manifest:
        grouped[item["label"]].append(item["path"])

    y_true, y_pred = [], []

    print("Testing ONLY held-out images that were not used for training.\n")

    for expected_idx, expected in enumerate(CLASS_NAMES):
        candidates = grouped.get(expected, [])[:]
        random.shuffle(candidates)
        selected = candidates[:MAX_PER_CLASS]

        print("=" * 72)
        print(f"EXPECTED CLASS: {expected.upper()}")
        print("=" * 72)

        for path in selected:
            image = load_image(path)
            probs = model.predict(tf.expand_dims(image, 0), verbose=0)[0]
            pred_idx = int(np.argmax(probs))
            pred = CLASS_NAMES[pred_idx]
            confidence = float(probs[pred_idx])
            status = "CORRECT" if pred_idx == expected_idx else "WRONG"

            print(
                f"{status:8s} | Expected: {expected:15s} | "
                f"Predicted: {pred:15s} | Confidence: {confidence * 100:6.2f}%"
            )
            print(
                "          probabilities -> " +
                ", ".join(f"{CLASS_NAMES[i]}={probs[i]*100:.1f}%" for i in range(len(CLASS_NAMES)))
            )
            y_true.append(expected_idx)
            y_pred.append(pred_idx)

    print("\n" + "=" * 72)
    print("RESULT SUMMARY")
    print("=" * 72)
    cm = confusion_matrix(y_true, y_pred, labels=range(len(CLASS_NAMES)))
    print("\nConfusion matrix (rows=true, columns=predicted):")
    print(cm)
    accuracy = (np.array(y_true) == np.array(y_pred)).mean() if y_true else 0.0
    print(f"\nSample accuracy: {accuracy * 100:.2f}%")
    print("\nClassification report:")
    print(classification_report(
        y_true,
        y_pred,
        labels=range(len(CLASS_NAMES)),
        target_names=CLASS_NAMES,
        digits=4,
        zero_division=0,
    ))

    counts = np.bincount(y_pred, minlength=len(CLASS_NAMES))
    if np.count_nonzero(counts) == 1:
        only = CLASS_NAMES[int(np.argmax(counts))]
        print(f"WARNING: The model still predicts only one class: {only}")
    else:
        print("GOOD: The model is producing more than one class.")


if __name__ == "__main__":
    main()
