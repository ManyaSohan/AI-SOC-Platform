import pandas as pd
import os
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    classification_report,
    confusion_matrix,
    recall_score,
    f1_score
)
from sklearn.utils import resample
import joblib
import json
import matplotlib.pyplot as plt
import seaborn as sns

# ================= DATASET =================
folder_path = r"C:\Users\User\OneDrive\Desktop\AI-SOC-Platform\dataset"

all_files = []
ROWS_PER_FILE = 15000

# Load datasets
for root, dirs, files in os.walk(folder_path):
    for file in files:
        if file.endswith(".csv") and (
            "unsw" in file.lower() or 
            "ciciot" in file.lower() or 
            "intrusion" in file.lower()
        ):
            full_path = os.path.join(root, file)
            print("Loading:", full_path)

            try:
                df = pd.read_csv(full_path, nrows=ROWS_PER_FILE, low_memory=False)
                all_files.append(df)
            except Exception as e:
                print("Skipping:", full_path, e)

# Combine all
data = pd.concat(all_files, ignore_index=True)
print("✅ Dataset loaded:", data.shape)

# Limit size (avoid crash)
if len(data) > 100000:
    data = data.sample(100000)
    print("⚠ Dataset reduced to:", data.shape)

# ================= LABEL =================
possible_labels = ['Label', 'label', 'Attack', 'attack', 'Class', 'class']

label_col = None
for col in possible_labels:
    if col in data.columns:
        label_col = col
        break

if label_col is None:
    print("❌ ERROR: No label column found!")
    exit()

print("✅ Using label column:", label_col)

# ================= FEATURES =================
y_raw = data[label_col]
X = data.drop(label_col, axis=1)

X = X.apply(pd.to_numeric, errors='coerce')
X.replace([np.inf, -np.inf], np.nan, inplace=True)
X = X.fillna(0)

# Convert labels
def convert_label(x):
    x = str(x).lower()
    if "benign" in x or "normal" in x or x == "0":
        return 0
    else:
        return 1

y = y_raw.apply(convert_label)

print("\nClass Distribution:\n", y.value_counts())

# ================= SPLIT =================
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

# ================= BALANCE =================
train_data = pd.concat([X_train, y_train], axis=1)

class_0 = train_data[train_data[label_col] == 0]
class_1 = train_data[train_data[label_col] == 1]

if len(class_0) > len(class_1):
    class_0_down = resample(class_0, replace=False,
                            n_samples=len(class_1), random_state=42)
    balanced_data = pd.concat([class_0_down, class_1])
else:
    class_1_down = resample(class_1, replace=False,
                            n_samples=len(class_0), random_state=42)
    balanced_data = pd.concat([class_0, class_1_down])

X_train = balanced_data.drop(label_col, axis=1)
y_train = balanced_data[label_col]

print("✅ Balanced dataset:", X_train.shape)

# ================= MODEL =================
model = RandomForestClassifier(
    n_estimators=300,
    max_depth=20,
    class_weight={0:1, 1:3}
)

model.fit(X_train, y_train)

# ================= PREDICTION =================
y_prob = model.predict_proba(X_test)[:,1]
y_pred = (y_prob > 0.25).astype(int)

# ================= METRICS =================
accuracy = accuracy_score(y_test, y_pred)
precision = precision_score(y_test, y_pred)
recall = recall_score(y_test, y_pred)
f1 = f1_score(y_test, y_pred)

report = classification_report(y_test, y_pred, output_dict=True)
cm = confusion_matrix(y_test, y_pred)

tn, fp, fn, tp = cm.ravel()
fpr = fp / (fp + tn)

print("\n📊 Model Performance:")
print("Accuracy:", accuracy)
print("Precision:", precision)
print("Recall:", recall)
print("F1 Score:", f1)

print("\n📄 Classification Report:")
print(classification_report(y_test, y_pred))

print("\nConfusion Matrix:\n", cm)

print(f"""
TN: {tn}
FP: {fp}
FN: {fn}
TP: {tp}
""")

# ================= SAVE METRICS (JSON SAFE) =================
metrics = {
    "accuracy": float(accuracy),
    "precision": float(precision),
    "recall": float(recall),
    "f1": float(f1),
    "fpr": float(fpr),

    "false_positives": int(fp),
    "false_negatives": int(fn),
    "true_positives": int(tp),
    "true_negatives": int(tn),

    "classification_report": report,
    "confusion_matrix": cm.tolist(),

    "dataset_total": int(5700000),
    "dataset_used": int(len(data))
}

with open("metrics.json", "w") as f:
    json.dump(metrics, f)

print("✅ Metrics saved")

# ================= CREATE STATIC FOLDER =================
if not os.path.exists("static"):
    os.makedirs("static")

# ================= CONFUSION MATRIX GRAPH =================
plt.figure(figsize=(5,4))
sns.heatmap(cm, annot=True, fmt='d', cmap='Blues')
plt.title("Confusion Matrix")
plt.xlabel("Predicted")
plt.ylabel("Actual")
plt.savefig("static/confusion_matrix.png")
plt.close()

# ================= PERFORMANCE GRAPH =================
plt.figure()
plt.bar(["Accuracy", "Precision", "Recall", "F1"],
        [accuracy, precision, recall, f1])
plt.title("Model Performance")
plt.savefig("static/performance.png")
plt.close()

print("✅ Graphs saved")

# ================= SAVE MODEL =================
if not os.path.exists("ai_model"):
    os.makedirs("ai_model")

joblib.dump(model, "ai_model/model.pkl")

print("\n✅ Model saved in ai_model/model.pkl")