"""
AI-SOC Platform — Model Training Script
========================================
Trains a Random Forest classifier on network intrusion datasets
(UNSW-NB15, CIC-IoT2023, or any labelled CSV dataset).

Usage:
    py -3.10 train_model.py

Outputs:
    ai_model/model.pkl       — trained model
    metrics.json             — evaluation metrics
    static/confusion_matrix.png
    static/performance.png
"""

import os
import json
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import joblib

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    classification_report,
    confusion_matrix,
)
from sklearn.utils import resample

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────
# CONFIGURATION — edit only this section
# ─────────────────────────────────────────────

# Path to folder containing your CSV datasets
DATASET_FOLDER = r"C:\Users\User\OneDrive\Desktop\AI-SOC-Platform Project\dataset"

# Keywords: any CSV whose filename contains one of these will be loaded
DATASET_KEYWORDS = ["unsw", "ciciot", "intrusion", "network", "iot"]

# Max rows loaded per file (increase if you have RAM)
ROWS_PER_FILE = 15000

# Max total rows after combining all files
MAX_TOTAL_ROWS = 100_000

# Random Forest hyperparameters
N_ESTIMATORS = 300
MAX_DEPTH = 20
ATTACK_CLASS_WEIGHT = 3      # higher = model penalises missing attacks more

# Decision threshold (lower = catch more attacks, more false positives)
THRESHOLD = 0.25

# Output paths
MODEL_PATH     = "ai_model/model.pkl"
METRICS_PATH   = "metrics.json"
STATIC_FOLDER  = "static"

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

POSSIBLE_LABEL_COLS = ["Label", "label", "Attack", "attack", "Class", "class", "category"]


def find_label_column(df: pd.DataFrame) -> str | None:
    """Return the first matching label column name, or None."""
    for col in POSSIBLE_LABEL_COLS:
        if col in df.columns:
            return col
    return None


def convert_label(value) -> int:
    """Map benign/normal → 0, everything else → 1 (attack)."""
    text = str(value).strip().lower()
    if text in ("0", "benign", "normal", "legitimate"):
        return 0
    return 1


def load_datasets(folder: str, keywords: list[str], rows_per_file: int) -> pd.DataFrame:
    """
    Walk folder recursively, load CSVs whose names match any keyword,
    and return a combined DataFrame.
    """
    all_frames: list[pd.DataFrame] = []

    print(f"\n📂 Searching for datasets in:\n   {folder}\n")

    if not os.path.exists(folder):
        raise FileNotFoundError(
            f"Dataset folder not found:\n  {folder}\n"
            "Please check DATASET_FOLDER in the configuration section."
        )

    for root, _, files in os.walk(folder):
        for file in files:
            if not file.lower().endswith(".csv"):
                continue
            if not any(kw in file.lower() for kw in keywords):
                continue

            full_path = os.path.join(root, file)
            print(f"  ⏳ Loading: {file}")

            try:
                df = pd.read_csv(full_path, nrows=rows_per_file, low_memory=False)

                # Drop completely empty columns
                df.dropna(axis=1, how="all", inplace=True)

                all_frames.append(df)
                print(f"     ✅ {len(df):,} rows | {df.shape[1]} columns")
            except Exception as exc:
                print(f"     ⚠️  Skipped ({exc})")

    if not all_frames:
        raise ValueError(
            "No matching CSV files found.\n"
            f"  Folder   : {folder}\n"
            f"  Keywords : {keywords}\n"
            "Make sure your CSVs are in that folder and their filenames contain "
            "one of the keywords above."
        )

    combined = pd.concat(all_frames, ignore_index=True)
    print(f"\n✅ Combined dataset: {combined.shape[0]:,} rows × {combined.shape[1]} columns")
    return combined


def preprocess(data: pd.DataFrame, label_col: str):
    """
    Split features / labels, coerce to numeric, handle inf/NaN.
    Returns X (DataFrame) and y (Series of 0/1).
    """
    y_raw = data[label_col]
    X = data.drop(columns=[label_col])

    # Drop non-numeric columns (IPs, timestamps, etc.)
    X = X.apply(pd.to_numeric, errors="coerce")
    X.replace([np.inf, -np.inf], np.nan, inplace=True)
    X.fillna(0, inplace=True)

    y = y_raw.apply(convert_label)
    return X, y


def balance_classes(X_train: pd.DataFrame, y_train: pd.Series, label_col: str):
    """Downsample majority class to match minority class size."""
    train_data = pd.concat([X_train, y_train.rename(label_col)], axis=1)

    class_0 = train_data[train_data[label_col] == 0]
    class_1 = train_data[train_data[label_col] == 1]

    if len(class_0) == 0 or len(class_1) == 0:
        print("⚠️  Only one class found — skipping balancing.")
        return X_train, y_train

    minority_size = min(len(class_0), len(class_1))

    class_0_bal = resample(class_0, replace=False, n_samples=minority_size, random_state=42)
    class_1_bal = resample(class_1, replace=False, n_samples=minority_size, random_state=42)

    balanced = pd.concat([class_0_bal, class_1_bal]).sample(frac=1, random_state=42)

    X_bal = balanced.drop(columns=[label_col])
    y_bal = balanced[label_col]

    print(f"✅ Balanced training set: {X_bal.shape[0]:,} rows (50 / 50)")
    return X_bal, y_bal


def save_plots(cm, accuracy, precision, recall, f1):
    """Save confusion matrix and performance bar chart to static/."""
    os.makedirs(STATIC_FOLDER, exist_ok=True)

    # Confusion matrix
    plt.figure(figsize=(6, 5))
    sns.heatmap(
        cm, annot=True, fmt="d", cmap="Blues",
        xticklabels=["Normal", "Attack"],
        yticklabels=["Normal", "Attack"],
    )
    plt.title("Confusion Matrix", fontsize=14, fontweight="bold")
    plt.xlabel("Predicted")
    plt.ylabel("Actual")
    plt.tight_layout()
    plt.savefig(os.path.join(STATIC_FOLDER, "confusion_matrix.png"), dpi=120)
    plt.close()
    print("✅ confusion_matrix.png saved")

    # Performance bar chart
    metrics_labels = ["Accuracy", "Precision", "Recall", "F1 Score"]
    metrics_values = [accuracy, precision, recall, f1]
    colors = ["#4CAF50", "#2196F3", "#FF9800", "#9C27B0"]

    plt.figure(figsize=(7, 4))
    bars = plt.bar(metrics_labels, metrics_values, color=colors, width=0.5)
    for bar, val in zip(bars, metrics_values):
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            f"{val:.3f}",
            ha="center", va="bottom", fontsize=11, fontweight="bold"
        )
    plt.ylim(0, 1.12)
    plt.title("Model Performance Metrics", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(os.path.join(STATIC_FOLDER, "performance.png"), dpi=120)
    plt.close()
    print("✅ performance.png saved")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  AI-SOC Platform — Model Training")
    print("=" * 55)

    # ── 1. Load data ──────────────────────────────────────
    data = load_datasets(DATASET_FOLDER, DATASET_KEYWORDS, ROWS_PER_FILE)

    if len(data) > MAX_TOTAL_ROWS:
        data = data.sample(MAX_TOTAL_ROWS, random_state=42)
        print(f"⚠️  Dataset sampled down to {MAX_TOTAL_ROWS:,} rows")

    # ── 2. Find label column ──────────────────────────────
    label_col = find_label_column(data)
    if label_col is None:
        print("\n❌ ERROR: Could not find a label column.")
        print(f"   Available columns: {list(data.columns)}")
        print(f"   Expected one of  : {POSSIBLE_LABEL_COLS}")
        return

    print(f"✅ Label column: '{label_col}'")

    # ── 3. Preprocess ─────────────────────────────────────
    X, y = preprocess(data, label_col)

    print("\nClass distribution:")
    for cls, count in y.value_counts().items():
        label = "Normal" if cls == 0 else "Attack"
        print(f"  {label} ({cls}): {count:,}")

    # ── 4. Train / test split ─────────────────────────────
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # ── 5. Balance training set ───────────────────────────
    X_train, y_train = balance_classes(X_train, y_train, label_col)

    # ── 6. Train model ────────────────────────────────────
    print(f"\n🤖 Training Random Forest ({N_ESTIMATORS} trees, max_depth={MAX_DEPTH}) ...")
    model = RandomForestClassifier(
        n_estimators=N_ESTIMATORS,
        max_depth=MAX_DEPTH,
        class_weight={0: 1, 1: ATTACK_CLASS_WEIGHT},
        n_jobs=-1,
        random_state=42,
    )
    model.fit(X_train, y_train)
    print("✅ Training complete")

    # ── 7. Evaluate ───────────────────────────────────────
    y_prob = model.predict_proba(X_test)[:, 1]
    y_pred = (y_prob > THRESHOLD).astype(int)

    accuracy  = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall    = recall_score(y_test, y_pred, zero_division=0)
    f1        = f1_score(y_test, y_pred, zero_division=0)
    report    = classification_report(y_test, y_pred, output_dict=True)
    cm        = confusion_matrix(y_test, y_pred)
    tn, fp, fn, tp = cm.ravel()
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    print("\n" + "─" * 40)
    print("📊 Model Performance")
    print("─" * 40)
    print(f"  Accuracy  : {accuracy:.4f}")
    print(f"  Precision : {precision:.4f}")
    print(f"  Recall    : {recall:.4f}")
    print(f"  F1 Score  : {f1:.4f}")
    print(f"  FPR       : {fpr:.4f}")
    print("─" * 40)
    print(f"  TP: {tp:,}   FP: {fp:,}")
    print(f"  TN: {tn:,}   FN: {fn:,}")
    print("─" * 40)
    print("\n" + classification_report(y_test, y_pred))

    # ── 8. Save metrics ───────────────────────────────────
    metrics = {
        "accuracy"  : float(accuracy),
        "precision" : float(precision),
        "recall"    : float(recall),
        "f1"        : float(f1),
        "fpr"       : float(fpr),
        "true_positives"  : int(tp),
        "true_negatives"  : int(tn),
        "false_positives" : int(fp),
        "false_negatives" : int(fn),
        "classification_report": report,
        "confusion_matrix"     : cm.tolist(),
        "dataset_total"        : 5_700_000,
        "dataset_used"         : int(len(data)),
    }

    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"✅ Metrics saved → {METRICS_PATH}")

    # ── 9. Save plots ─────────────────────────────────────
    save_plots(cm, accuracy, precision, recall, f1)

    # ── 10. Save model ────────────────────────────────────
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"✅ Model saved  → {MODEL_PATH}")

    print("\n🎉 Done! You can now run your Flask app.\n")


if __name__ == "__main__":
    main()
