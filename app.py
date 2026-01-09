from flask import Flask, request, render_template, redirect, session
import sqlite3
from textblob import TextBlob
from cryptography.fernet import Fernet
import os

app = Flask(__name__)
app.secret_key = "nyayamitra_lock_key"  # required for lock/session

# ---------------- ENCRYPTION (STABLE KEY) ----------------

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
            case_id TEXT,
            user_id INTEGER,
            user_role TEXT,
            encrypted_note TEXT,
            sentiment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------- ROUTES ----------------

@app.route("/")
def home():
    # if locked, do not show notes
    return render_template("notes.html", notes=[])

@app.route("/add-note", methods=["POST"])
def add_note():
    case_id = request.form["case_id"]
    note = request.form["note"]

    user_id = 1
    user_role = "Judge"

    encrypted_note = encrypt_text(note)
    sentiment = get_sentiment(note)

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO case_notes
        (case_id, user_id, user_role, encrypted_note, sentiment)
        VALUES (?, ?, ?, ?, ?)
    """, (case_id, user_id, user_role, encrypted_note, sentiment))
    conn.commit()
    conn.close()

    return redirect("/")

@app.route("/view")
def redirect_to_notes():
    case_id = request.args.get("case_id")
    session["unlocked"] = True   # unlock notes
    return redirect(f"/notes/{case_id}")

@app.route("/notes/<case_id>")
def view_notes(case_id):
    if not session.get("unlocked"):
        return redirect("/")

    user_id = 1
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT encrypted_note, sentiment, created_at
        FROM case_notes
        WHERE case_id=? AND user_id=?
        ORDER BY created_at DESC
    """, (case_id, user_id))

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

