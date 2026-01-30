from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
import hashlib

app = Flask(__name__)

# ---------- DB helpers ----------

def get_db():
    return sqlite3.connect("users.db")

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT,
            password TEXT
        )
    """)
    # If table existed without email column, try to add it
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

# ---------- API ROUTES (for keystrokes) ----------

@app.route("/api/enroll", methods=["POST"])
def api_enroll():
    data = request.get_json()
    print("Enroll data received:", data)

    if data is None:
        return jsonify({"status": "error", "message": "No JSON received"}), 400
    if "username" not in data or "events" not in data:
        return jsonify({"status": "error", "message": "Invalid format"}), 400

    return jsonify({
        "status": "ok",
        "received": True,
        "event_count": len(data["events"])
    })

@app.route("/api/login-try", methods=["POST"])
def api_login_try():
    data = request.get_json()
    print("Login keystroke data received:", data)

    if data is None:
        return jsonify({"status": "error", "message": "No JSON received"}), 400

    # Later: compare with stored profile and return match result
    return jsonify({
        "status": "ok",
        "received": True
    })

# ---------- ROUTES (HTML pages) ----------

@app.route("/", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT password FROM users WHERE username = ?",
            (username,)
        )
        row = cursor.fetchone()
        conn.close()

        if row is None:
            error = "Invalid username or password. Please try again or register first."
        else:
            stored_hashed = row[0]
            if stored_hashed == hash_password(password):
                return redirect(url_for("home", username=username))
            else:
                error = "Invalid username or password. Please try again or register first."

    return render_template("login.html", error=error)

@app.route("/register", methods=["GET", "POST"])
def register():
    message = None
    error = None

    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]

        hashed_password = hash_password(password)

        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                (username, email, hashed_password)
            )
            conn.commit()
            conn.close()
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            error = "Username already exists. Choose another one."

    return render_template("register.html", error=error, message=message)

@app.route("/home")
def home():
    username = request.args.get("username")
    return render_template("home.html", username=username)

@app.route("/enroll", methods=["GET", "POST"])
def enroll():
    message = None
    error = None

    if request.method == "POST":
        password = request.form["password"]
        if password:
            message = "Password sample received. Keystroke timings will be processed in the backend."
        else:
            error = "Please type the password before submitting."

    return render_template("enroll.html", message=message, error=error)

# ---------- Keystroke helper (future use) ----------

def extract_timings(events):
    dwell_times = []
    flight_times = []
    return {
        "dwell": dwell_times,
        "flight": flight_times
    }

# ---------- MAIN ----------

if __name__ == "__main__":
    init_db()
    app.run(debug=True)



