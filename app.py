from flask import Flask, request, jsonify, render_template, session, redirect
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import numpy as np
import joblib
import pandas as pd
import random
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = "secret123"

DB = "soc.db"

# ================= DB =================
def init_db():
    con = sqlite3.connect(DB)
    c = con.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        password TEXT,
        role TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS incidents(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip TEXT,
        attack TEXT,
        risk INTEGER,
        status TEXT,
        analyst TEXT,
        comment TEXT
    )
    """)

    c.execute("SELECT * FROM users")
    if not c.fetchone():
        c.execute("""
        INSERT INTO users(username,password,role)
        VALUES(?,?,?)
        """, ("admin", generate_password_hash("admin123"), "admin"))

    con.commit()
    con.close()

init_db()

# ================= MODEL =================
try:
    model = joblib.load("ai_model/model.pkl")
    print("✅ Model loaded")
except Exception as e:
    print("❌ Model load failed:", e)
    model = None

# ================= DATASET =================
df = pd.read_csv("dataset/integrated_dataset_ultrafast/integrated_ciciot2023_dataset.csv")
countries = ["India","USA","Germany","Brazil","China","Russia","UK"]

# ================= LOAD METRICS =================
with open("metrics.json") as f:
    metrics = json.load(f)

# ================= LOGIN =================
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        con = sqlite3.connect(DB)
        c = con.cursor()
        c.execute("SELECT password,role FROM users WHERE username=?", (u,))
        r = c.fetchone()
        con.close()

        if r and check_password_hash(r[0], p):
            session["user"] = u
            session["role"] = r[1]
            return redirect("/")
        return "Invalid login"

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ================= DASHBOARD =================
@app.route("/")
def home():
    if "user" not in session:
        return redirect("/login")
    return render_template("dashboard.html", role=session.get("role"))

# ================= HISTORY =================
@app.route("/history")
def history():
    return render_template("history.html")

@app.route("/api/history")
def api_history():
    return logs()

# ================= INCIDENTS =================
@app.route("/incidents")
def incidents_page():
    return render_template("incidents.html", role=session.get("role"))

@app.route("/api/incidents")
def api_incidents():
    con = sqlite3.connect(DB)
    c = con.cursor()
    c.execute("SELECT * FROM incidents")
    data = c.fetchall()
    con.close()
    return jsonify(data)

# ================= REPORT =================
@app.route("/report")
def report():

    con = sqlite3.connect(DB)
    c = con.cursor()
    c.execute("SELECT * FROM incidents ORDER BY id DESC")
    rows = c.fetchall()
    con.close()

    total = len(rows)
    high = sum(1 for r in rows if r[3] >= 70)
    medium = sum(1 for r in rows if 40 <= r[3] < 70)
    low = sum(1 for r in rows if r[3] < 40)

    top_ip = max(rows, key=lambda x: x[3])[1] if rows else "N/A"
    top_risk = max(rows, key=lambda x: x[3])[3] if rows else 0

    # ================= METRICS =================
    recall = metrics["recall"]
    f1 = metrics["f1"]
    fpr = metrics["fpr"]

    fp = metrics["false_positives"]
    fn = metrics["false_negatives"]
    tp = metrics["true_positives"]
    tn = metrics["true_negatives"]

    return render_template(
        "report.html",
        name="Manya Sohan D.H, Rishitha Suhani D Souza, Sanskrithi, Sanjana V Hathwar",
        report_id=f"SOC-{random.randint(1000000000,9999999999)}",
        time=datetime.now(),
        total=total,
        high=high,
        medium=medium,
        low=low,
        top_attack="DDoS",
        top_ip=top_ip,
        top_risk=top_risk,
        peak_time=datetime.now(),
        data=rows,

        # BASIC METRICS
        accuracy=metrics["accuracy"],
        precision=metrics["precision"],
        report_data=metrics["classification_report"],
        dataset_total=metrics["dataset_total"],
        dataset_used=metrics["dataset_used"],

        # ADVANCED METRICS
        recall=recall,
        f1=f1,
        fpr=fpr,
        fp=fp,
        fn=fn,
        tp=tp,
        tn=tn
    )

# ================= AI PREDICT =================
@app.route("/predict", methods=["POST"])
def predict():
    data = request.json

    packets = data.get("packets", 0)
    login_fail = data.get("login_fail", 0)
    sql = data.get("sql", 0)

    features = [0]*322
    features[0] = packets
    features[1] = login_fail
    features[2] = sql

    features = np.array(features).reshape(1,-1)

    if model is None:
        return jsonify({"error":"Model not loaded"})

    prob = model.predict_proba(features)[0][1]
    attack = "Attack" if prob > 0.25 else "Normal"

    if attack == "Attack":
        con = sqlite3.connect(DB)
        c = con.cursor()
        c.execute("""
        INSERT INTO incidents(ip,attack,risk,status)
        VALUES(?,?,?,?)
        """, ("127.0.0.1", attack, int(prob*100), "Open"))
        con.commit()
        con.close()

    return jsonify({"attack":attack,"probability":float(prob)})

# ================= LOGS =================
@app.route("/logs")
def logs():
    sample = df.sample(10)
    data = []

    for i, row in sample.iterrows():

        label = str(row.iloc[-1]).lower()

        if "benign" in label or "normal" in label or label == "0":
            attack = "Normal"
            severity = "Low"
        else:
            attack = "Attack"
            severity = "High"

        data.append([
            i,
            f"{random.randint(1,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(0,255)}",
            random.choice(countries),
            random.randint(100,3000),
            random.randint(0,1),
            random.randint(0,1),
            attack,
            severity,
            random.randint(20,100),
            "T1499",
            0,
            0,
            "Execution",
            datetime.now().strftime("%H:%M:%S")
        ])

    return jsonify(data)

# ================= INCIDENT ACTIONS =================
@app.route("/close_incident/<int:id>")
def close_incident(id):
    con = sqlite3.connect(DB)
    c = con.cursor()
    c.execute("UPDATE incidents SET status='Closed' WHERE id=?", (id,))
    con.commit()
    con.close()
    return "OK"

@app.route("/update_incident/<int:id>", methods=["POST"])
def update_incident(id):
    analyst = request.form.get("analyst")
    comment = request.form.get("comment")

    con = sqlite3.connect(DB)
    c = con.cursor()

    if analyst:
        c.execute("UPDATE incidents SET analyst=? WHERE id=?", (analyst,id))
    if comment:
        c.execute("UPDATE incidents SET comment=? WHERE id=?", (comment,id))

    con.commit()
    con.close()
    return "OK"

# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)