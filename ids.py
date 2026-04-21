import joblib
import numpy as np

model = joblib.load("ai_model/model.pkl")

def detect_attack(features):
    features = np.array(features).reshape(1, -1)

    prob = model.predict_proba(features)[0][1]

    if prob > 0.25:
        return "Attack", prob
    else:
        return "Normal", prob