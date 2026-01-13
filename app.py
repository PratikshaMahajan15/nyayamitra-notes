from flask import Flask, request, render_template, redirect, session, jsonify
import sqlite3
from textblob import TextBlob
from cryptography.fernet import Fernet
import os

app = Flask(__name__)
app.secret_key = "nyayamitra_lock_key"

# ---------------- ENCRYPTION ----------------

KEY_FILE = "secret.key"

if not os.path.exists(KEY_FILE):
    with open(KEY_FILE, "wb") as f:
        f.write(Fernet.generate_key())

with open(KEY_FILE, "rb") as f:
    key = f.read()

cipher = Fernet(key)

def encrypt_text(text):
    return cipher.encrypt(text.encode()).decode()

def decrypt_text(text):
    return cipher.decrypt(text.encode()).decode()

# ---------------- SENTIMENT (LEGAL-AWARE) ----------------

def get_sentiment(note):
    text = note.lower()

    legal_negative_words = [
        "delay", "delaying", "adjournment", "pending",
        "missing", "non-compliance", "default",
        "intentionally", "absent", "ignored"
    ]

    for word in legal_negative_words:
        if word in text:
            return "Negative"

    polarity = TextBlob(note).sentiment.polarity
    if polarity > 0.2:
        return "Positive"
    elif polarity < -0.2:
        return "Negative"
    else:
        return "Neutral"

# ---------------- DATABASE ----------------

def init_db():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS case_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cnr_number TEXT,
            encrypted_note TEXT,
            sentiment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------- UI ROUTES ----------------

@app.route("/")
def home():
    return render_template("notes.html", notes=[])

@app.route("/add-note", methods=["POST"])
def add_note():
    cnr = request.form["cnr"]
    note = request.form["note"]

    encrypted_note = encrypt_text(note)
    sentiment = get_sentiment(note)

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO case_notes (cnr_number, encrypted_note, sentiment)
        VALUES (?, ?, ?)
    """, (cnr, encrypted_note, sentiment))
    conn.commit()
    conn.close()

    return redirect("/")

@app.route("/view")
def view_redirect():
    cnr = request.args.get("cnr")
    session["unlocked"] = True
    return redirect(f"/notes/{cnr}")

@app.route("/notes/<cnr>")
def view_notes(cnr):
    if not session.get("unlocked"):
        return redirect("/")

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT encrypted_note, sentiment, created_at
        FROM case_notes
        WHERE cnr_number=?
        ORDER BY created_at DESC
    """, (cnr,))

    notes = []
    for row in cur.fetchall():
        notes.append({
            "note": decrypt_text(row[0]),
            "sentiment": row[1],
            "time": row[2]
        })

    conn.close()
    return render_template("notes.html", notes=notes)

@app.route("/lock")
def lock_notes():
    session.pop("unlocked", None)
    return redirect("/")

# ---------------- JSON API ----------------

@app.route("/api/notes/<cnr>")
def api_notes(cnr):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT encrypted_note, sentiment, created_at
        FROM case_notes
        WHERE cnr_number=?
        ORDER BY created_at DESC
    """, (cnr,))

    notes = []
    for row in cur.fetchall():
        notes.append({
            "note": decrypt_text(row[0]),
            "sentiment": row[1],
            "timestamp": row[2]
        })

    conn.close()

    return jsonify({
        "cnr_number": cnr,
        "total_notes": len(notes),
        "notes": notes
    })

# ---------------- DOCS ----------------

@app.route("/docs")
def docs():
    return jsonify({
        "service": "NyayaMitra Secure Notes API",
        "base_url": "https://nyayamitra-notes.onrender.com",
        "description": "Encrypted case notes with AI-based sentiment analysis",
        "endpoints": {
            "/": "UI to add and view private case notes",
            "/api/notes/{CNR}": {
                "method": "GET",
                "description": "Returns all notes for a given CNR in JSON",
                "example": {
                    "cnr_number": "KAHC010000242018",
                    "total_notes": 1,
                    "notes": [
                        {
                            "note": "Opposite party delaying intentionally",
                            "sentiment": "Negative",
                            "timestamp": "YYYY-MM-DD HH:MM:SS"
                        }
                    ]
                }
            },
            "/lock": "Locks notes using session security"
        }
    })

# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
