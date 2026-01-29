from flask import Flask, render_template, request, redirect, url_for
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
    # Create table if it does not exist (with email column)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT,
            password TEXT
        )
    """)
    # Try to add email column if table already existed without it
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
    except sqlite3.OperationalError:
        # Column already exists or table just created – ignore
        pass

    conn.commit()
    conn.close()

# ---------- ROUTES ----------

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
                return f"<h3>Logged in as {username}!</h3><br><a href='/'>Back</a>"
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

# ---------- MAIN ----------

if __name__ == "__main__":
    init_db()
    app.run(debug=True)

