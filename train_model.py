from pathlib import Path
import json
import random
import numpy as np
import tensorflow as tf
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_class_weight
from sklearn.metrics import classification_report, confusion_matrix, f1_score

# ==============================
# CONFIG
# ==============================
BASE_DIR = Path(__file__).resolve().parent
DATASET_DIR = BASE_DIR / "dataset"
MODEL_PATH = BASE_DIR / "waste_classifier.keras"
META_PATH = BASE_DIR / "class_names.json"
TEST_MANIFEST = BASE_DIR / "test_manifest.json"

CLASS_NAMES = ["biodegradable", "recyclable", "residual"]
IMG_SIZE = 224
BATCH_SIZE = 16
SEED = 123
INITIAL_EPOCHS = 15
FINE_TUNE_EPOCHS = 20
MIN_IMAGES_PER_CLASS = 20

random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def collect_files():
    paths, labels = [], []
    print("\nDataset counts:")
    for idx, class_name in enumerate(CLASS_NAMES):
        folder = DATASET_DIR / class_name
        if not folder.exists():
            raise FileNotFoundError(f"Missing class folder: {folder}")
        files = sorted([p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS])
        print(f"  {class_name:15s}: {len(files)}")
        if len(files) < MIN_IMAGES_PER_CLASS:
            raise ValueError(
                f"'{class_name}' has only {len(files)} images. "
                f"Please use at least {MIN_IMAGES_PER_CLASS} varied images for this class."
            )
        paths.extend([str(p) for p in files])
        labels.extend([idx] * len(files))
    return np.array(paths), np.array(labels, dtype=np.int32)


def stratified_split(paths, labels):
    # 70% train, 15% validation, 15% held-out test
    train_p, temp_p, train_y, temp_y = train_test_split(
        paths, labels,
        test_size=0.30,
        random_state=SEED,
        stratify=labels,
    )
    val_p, test_p, val_y, test_y = train_test_split(
        temp_p, temp_y,
        test_size=0.50,
        random_state=SEED,
        stratify=temp_y,
    )
    return train_p, train_y, val_p, val_y, test_p, test_y


def decode_image(path, label):
    image = tf.io.read_file(path)
    image = tf.io.decode_image(image, channels=3, expand_animations=False)
    image.set_shape([None, None, 3])
    image = tf.image.resize(image, [IMG_SIZE, IMG_SIZE])
    image = tf.cast(image, tf.float32)  # 0..255
    return image, label


# IMPORTANT: augmentation is used only by the training dataset.
AUGMENT = tf.keras.Sequential([
    tf.keras.layers.RandomFlip("horizontal"),
    tf.keras.layers.RandomRotation(0.08),
    tf.keras.layers.RandomZoom(0.10),
    tf.keras.layers.RandomTranslation(0.06, 0.06),
    tf.keras.layers.RandomContrast(0.10),
], name="train_only_augmentation")


def augment_image(image, label):
    image = AUGMENT(image, training=True)
    image = tf.clip_by_value(image, 0.0, 255.0)
    return image, label


def make_dataset(paths, labels, training=False):
    ds = tf.data.Dataset.from_tensor_slices((paths, labels))
    if training:
        ds = ds.shuffle(len(paths), seed=SEED, reshuffle_each_iteration=True)
    ds = ds.map(decode_image, num_parallel_calls=tf.data.AUTOTUNE)
    if training:
        ds = ds.map(augment_image, num_parallel_calls=tf.data.AUTOTUNE)
    ds = ds.batch(BATCH_SIZE)
    ds = ds.prefetch(tf.data.AUTOTUNE)
    return ds


def make_model():
    inputs = tf.keras.Input(shape=(IMG_SIZE, IMG_SIZE, 3), name="image")

    # MobileNetV2 expects pixels in [-1, 1].
    # This preprocessing is INSIDE the saved model, so all inference code
    # should send ordinary RGB float pixels in the 0..255 range.
    x = tf.keras.layers.Rescaling(1.0 / 127.5, offset=-1, name="mobilenet_preprocess")(inputs)

    base = tf.keras.applications.MobileNetV2(
        input_shape=(IMG_SIZE, IMG_SIZE, 3),
        include_top=False,
        weights="imagenet",
    )
    base.trainable = False
    x = base(x, training=False)
    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    x = tf.keras.layers.Dropout(0.35)(x)
    x = tf.keras.layers.Dense(
        128,
        activation="relu",
        kernel_regularizer=tf.keras.regularizers.l2(1e-4),
    )(x)
    x = tf.keras.layers.Dropout(0.25)(x)
    outputs = tf.keras.layers.Dense(len(CLASS_NAMES), activation="softmax", name="waste_class")(x)
    model = tf.keras.Model(inputs, outputs)
    return model, base


def print_split_counts(name, labels):
    counts = np.bincount(labels, minlength=len(CLASS_NAMES))
    print(f"\n{name} split:")
    for i, c in enumerate(counts):
        print(f"  {CLASS_NAMES[i]:15s}: {int(c)}")


def main():
    print("TensorFlow:", tf.__version__)
    print("Dataset:", DATASET_DIR)

    paths, labels = collect_files()
    train_p, train_y, val_p, val_y, test_p, test_y = stratified_split(paths, labels)

    print_split_counts("TRAIN", train_y)
    print_split_counts("VALIDATION", val_y)
    print_split_counts("TEST", test_y)

    # Save exact held-out test files so test_model.py never tests training images.
    manifest = [
        {"path": str(Path(p).resolve()), "label": CLASS_NAMES[int(y)]}
        for p, y in zip(test_p, test_y)
    ]
    TEST_MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    train_ds = make_dataset(train_p, train_y, training=True)
    val_ds = make_dataset(val_p, val_y, training=False)
    test_ds = make_dataset(test_p, test_y, training=False)

    weights = compute_class_weight(
        class_weight="balanced",
        classes=np.arange(len(CLASS_NAMES)),
        y=train_y,
    )
    class_weights = {i: float(w) for i, w in enumerate(weights)}
    print("\nClass weights:")
    for i, w in class_weights.items():
        print(f"  {CLASS_NAMES[i]:15s}: {w:.3f}")

    model, base = make_model()
    model.compile(
        optimizer=tf.keras.optimizers.Adam(3e-4),
        loss=tf.keras.losses.SparseCategoricalCrossentropy(),
        metrics=["accuracy"],
    )

    callbacks = [
        tf.keras.callbacks.ModelCheckpoint(
            MODEL_PATH,
            monitor="val_loss",
            save_best_only=True,
            verbose=1,
        ),
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=5,
            restore_best_weights=True,
            verbose=1,
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.3,
            patience=2,
            min_lr=1e-7,
            verbose=1,
        ),
    ]

    print("\n=== STAGE 1: TRAIN CLASSIFIER HEAD ===")
    model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=INITIAL_EPOCHS,
        class_weight=class_weights,
        callbacks=callbacks,
        verbose=1,
    )

    # Fine tune only the last part of MobileNetV2.
    print("\n=== STAGE 2: FINE TUNE MOBILENETV2 ===")
    base.trainable = True
    fine_tune_at = max(0, len(base.layers) - 35)
    for layer in base.layers[:fine_tune_at]:
        layer.trainable = False
    # BatchNorm layers remain frozen for stable transfer learning.
    for layer in base.layers:
        if isinstance(layer, tf.keras.layers.BatchNormalization):
            layer.trainable = False

    model.compile(
        optimizer=tf.keras.optimizers.Adam(1e-5),
        loss=tf.keras.losses.SparseCategoricalCrossentropy(),
        metrics=["accuracy"],
    )

    callbacks2 = [
        tf.keras.callbacks.ModelCheckpoint(
            MODEL_PATH,
            monitor="val_loss",
            save_best_only=True,
            verbose=1,
        ),
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=6,
            restore_best_weights=True,
            verbose=1,
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.3,
            patience=2,
            min_lr=1e-7,
            verbose=1,
        ),
    ]

    model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=FINE_TUNE_EPOCHS,
        class_weight=class_weights,
        callbacks=callbacks2,
        verbose=1,
    )

    print("\nLoading best saved model...")
    best = tf.keras.models.load_model(MODEL_PATH)

    print("\n=== HELD-OUT TEST ===")
    test_loss, test_acc = best.evaluate(test_ds, verbose=0)
    probs = best.predict(test_ds, verbose=0)
    pred_y = np.argmax(probs, axis=1)

    macro_f1 = f1_score(test_y, pred_y, average="macro")
    print(f"Test accuracy: {test_acc * 100:.2f}%")
    print(f"Macro F1:      {macro_f1 * 100:.2f}%")
    print("\nConfusion matrix (rows=true, columns=predicted):")
    print(confusion_matrix(test_y, pred_y, labels=np.arange(len(CLASS_NAMES))))
    print("\nClassification report:")
    print(classification_report(
        test_y,
        pred_y,
        labels=np.arange(len(CLASS_NAMES)),
        target_names=CLASS_NAMES,
        digits=4,
        zero_division=0,
    ))

    per_class_recall = []
    cm = confusion_matrix(test_y, pred_y, labels=np.arange(len(CLASS_NAMES)))
    for i, name in enumerate(CLASS_NAMES):
        denom = cm[i].sum()
        recall = (cm[i, i] / denom) if denom else 0.0
        per_class_recall.append(float(recall))
        print(f"Recall {name:15s}: {recall * 100:.2f}%")

    meta = {
        "class_names": CLASS_NAMES,
        "image_size": IMG_SIZE,
        "input_contract": "RGB float32 pixels in 0..255; preprocessing is inside the model",
        "test_accuracy": float(test_acc),
        "macro_f1": float(macro_f1),
        "per_class_recall": {
            CLASS_NAMES[i]: per_class_recall[i] for i in range(len(CLASS_NAMES))
        },
    }
    META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print("\n=== RELIABILITY CHECK ===")
    if min(per_class_recall) >= 0.80 and macro_f1 >= 0.80:
        print("PASS: All three classes reached at least 80% recall and macro F1 >= 80%.")
    else:
        weakest = int(np.argmin(per_class_recall))
        print("NOT YET RELIABLE ENOUGH.")
        print(f"Weakest class: {CLASS_NAMES[weakest]} ({per_class_recall[weakest] * 100:.2f}% recall)")
        print("Improve that class with more varied, correctly labeled images and retrain.")

    print(f"\nSaved model: {MODEL_PATH}")
    print(f"Saved metadata: {META_PATH}")
    print(f"Saved held-out test manifest: {TEST_MANIFEST}")


if __name__ == "__main__":
    main()
