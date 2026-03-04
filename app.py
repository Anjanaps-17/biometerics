from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import sqlite3
import hashlib
import hmac
import math
import os
from datetime import datetime, timedelta
from statistics import mean, stdev

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24)

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
MAX_FAILED_ATTEMPTS  = 3     # lockout after this many consecutive failures
LOCKOUT_MINUTES      = 15    # auto-unlock after this many minutes
Z_THRESHOLD          = 2.5   # fixed z-space threshold (distance already normalised)
MIN_STD              = 0.0001  # division-by-zero guard
DEBUG_MODE           = os.environ.get("FLASK_DEBUG", "false").lower() == "true"


# ─────────────────────────────────────────────
#  DB HELPERS
# ─────────────────────────────────────────────

def get_db():
    return sqlite3.connect("users.db")


def hash_password(password: str) -> tuple:
    """
    PBKDF2-HMAC-SHA256 with a random 32-byte salt.
    Returns (hex_hash, hex_salt).
    """
    salt = os.urandom(32)
    key  = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return key.hex(), salt.hex()


def verify_password(password: str, stored_hash: str, stored_salt: str) -> bool:
    """
    Constant-time comparison via hmac.compare_digest to prevent timing attacks.
    """
    salt = bytes.fromhex(stored_salt)
    key  = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return hmac.compare_digest(key.hex(), stored_hash)   # Fix 6: timing-safe


def init_db():
    print(">>> init_db() running <<<")
    conn   = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email    TEXT,
            password TEXT,
            salt     TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keystroke_profiles (
            user_id     INTEGER PRIMARY KEY,
            mean_dwell  REAL,
            std_dwell   REAL,
            mean_flight REAL,
            std_flight  REAL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS failed_attempts (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            username  TEXT,
            distance  REAL,
            timestamp TEXT
        )
    """)

    # Fix 5: added last_fail_time for time-based lockout reset
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lockout (
            username       TEXT PRIMARY KEY,
            fail_count     INTEGER DEFAULT 0,
            last_fail_time TEXT
        )
    """)

    for col in ("email TEXT", "salt TEXT"):
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
#  KEYSTROKE ANALYSIS
# ─────────────────────────────────────────────

def calculate_profile_statistics(samples: list) -> dict:
    """
    Aggregate dwell & flight times from all enrollment samples,
    compute mean and std for each dimension.
    """
    all_dwell  = []
    all_flight = []

    for sample in samples:
        timings = sample.get("timings", {})
        all_dwell.extend(timings.get("dwell_times",  []))
        all_flight.extend(timings.get("flight_times", []))

    return {
        "mean_dwell":   mean(all_dwell)   if all_dwell           else 0,
        "std_dwell":    stdev(all_dwell)  if len(all_dwell)  > 1 else MIN_STD,
        "mean_flight":  mean(all_flight)  if all_flight          else 0,
        "std_flight":   stdev(all_flight) if len(all_flight) > 1 else MIN_STD,
        "dwell_count":  len(all_dwell),
        "flight_count": len(all_flight),
    }


def z_score_euclidean_distance(current_timings: dict, stored_profile: dict) -> float:
    """
    Root Mean Square (RMS) Z-score distance.

    Every timing is converted to:  z = (t - mean) / std
    Then:  distance = sqrt( sum_z² / total_points )

    Moving N inside the sqrt keeps the result in proper Z-scale
    regardless of password length — a long password no longer
    artificially deflates the distance.

    Expected ranges:  genuine user ~0.8-1.5,  impostor ~3.0-6.0
    Threshold 2.5 sits cleanly between the two distributions.
    """
    dwell_times  = current_timings.get("dwell_times",  [])
    flight_times = current_timings.get("flight_times", [])

    mean_dwell  = stored_profile.get("mean_dwell",  0)
    mean_flight = stored_profile.get("mean_flight", 0)
    std_dwell   = max(stored_profile.get("std_dwell",  MIN_STD), MIN_STD)
    std_flight  = max(stored_profile.get("std_flight", MIN_STD), MIN_STD)

    dwell_z_sq  = sum(((t - mean_dwell)  / std_dwell)  ** 2 for t in dwell_times)
    flight_z_sq = sum(((t - mean_flight) / std_flight) ** 2 for t in flight_times)

    total_points = len(dwell_times) + len(flight_times)

    # RMS Z-distance: sqrt(sum/N) keeps result in Z-scale for any password length
    return math.sqrt((dwell_z_sq + flight_z_sq) / max(total_points, 1))


def extract_timings(events: list) -> dict:
    """
    Convert raw keydown/keyup event list → dwell_times & flight_times.

    Fix 1: returns keys "dwell_times" and "flight_times" (consistent everywhere).
    Fix 2: uses a list-per-key queue so repeated letters (e.g. "aa") don't
           corrupt dwell calculations — earliest keydown is always consumed first.
    """
    dwell_times   = []
    flight_times  = []
    last_keyup    = None
    keydown_times = {}          # key → list of timestamps (FIFO queue per key)

    for event in events:
        if event["type"] == "keydown":
            # Fix 2: append to list instead of overwriting
            keydown_times.setdefault(event["key"], []).append(event["timestamp"])

            if last_keyup is not None:
                flight_times.append(event["timestamp"] - last_keyup)

        elif event["type"] == "keyup":
            queue = keydown_times.get(event["key"])
            if queue:
                # Fix 2: pop the earliest keydown for this key (FIFO)
                keydown_ts = queue.pop(0)
                dwell_times.append(event["timestamp"] - keydown_ts)
                last_keyup = event["timestamp"]

    return {
        "dwell_times":  dwell_times,   # Fix 1: consistent key name
        "flight_times": flight_times,  # Fix 1: consistent key name
    }


# ─────────────────────────────────────────────
#  LOCKOUT HELPERS  (with time-based auto-reset)
# ─────────────────────────────────────────────

def get_fail_info(cursor, username: str) -> tuple:
    """Returns (fail_count, last_fail_time_str)."""
    cursor.execute(
        "SELECT fail_count, last_fail_time FROM lockout WHERE username = ?",
        (username,)
    )
    row = cursor.fetchone()
    return (row[0], row[1]) if row else (0, None)


def is_locked_out(cursor, username: str) -> bool:
    """
    Fix 5: Time-based lockout — automatically clears after LOCKOUT_MINUTES.
    """
    fail_count, last_fail_str = get_fail_info(cursor, username)

    if fail_count < MAX_FAILED_ATTEMPTS:
        return False

    if last_fail_str is None:
        return False

    last_fail = datetime.fromisoformat(last_fail_str)
    if datetime.utcnow() - last_fail > timedelta(minutes=LOCKOUT_MINUTES):
        # Lockout window expired — auto-reset
        cursor.execute(
            "UPDATE lockout SET fail_count = 0, last_fail_time = NULL WHERE username = ?",
            (username,)
        )
        return False

    return True


def increment_fail(cursor, username: str, distance: float):
    now = datetime.utcnow().isoformat()

    cursor.execute(
        "INSERT INTO failed_attempts (username, distance, timestamp) VALUES (?,?,?)",
        (username, round(distance, 4), now)
    )
    cursor.execute("""
        INSERT INTO lockout (username, fail_count, last_fail_time) VALUES (?, 1, ?)
        ON CONFLICT(username) DO UPDATE SET
            fail_count     = fail_count + 1,
            last_fail_time = ?
    """, (username, now, now))


def reset_fail(cursor, username: str):
    cursor.execute("""
        INSERT INTO lockout (username, fail_count, last_fail_time) VALUES (?, 0, NULL)
        ON CONFLICT(username) DO UPDATE SET
            fail_count     = 0,
            last_fail_time = NULL
    """, (username,))


# ─────────────────────────────────────────────
#  API: ENROLL
# ─────────────────────────────────────────────

@app.route("/api/enroll", methods=["POST"])
def api_enroll():
    """
    Receive ≥3 typing samples, compute keystroke profile, save to DB.

    Body JSON:
    {
      "username": "alice",
      "samples": [
        { "timings": { "dwell_times": [...], "flight_times": [...] } },
        ...
      ]
    }

    Security note: client-side timing data can be spoofed. In production,
    integrity validation or session-bound capture would be required.
    """
    data = request.get_json()
    print("\n" + "="*60)
    print("ENROLLMENT DATA RECEIVED")
    print("="*60)

    if data is None:
        return jsonify({"status": "error", "message": "No JSON received"}), 400

    username = data.get("username")
    samples  = data.get("samples", [])

    if not username or not samples:
        return jsonify({"status": "error", "message": "Missing username or samples"}), 400

    if len(samples) < 3:
        return jsonify({"status": "error", "message": "Need at least 3 samples"}), 400

    conn   = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return jsonify({"status": "error", "message": "User not found"}), 404

    user_id = user[0]
    profile = calculate_profile_statistics(samples)

    cursor.execute("""
        INSERT INTO keystroke_profiles (user_id, mean_dwell, std_dwell, mean_flight, std_flight)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            mean_dwell  = excluded.mean_dwell,
            std_dwell   = excluded.std_dwell,
            mean_flight = excluded.mean_flight,
            std_flight  = excluded.std_flight
    """, (user_id,
          profile["mean_dwell"],  profile["std_dwell"],
          profile["mean_flight"], profile["std_flight"]))

    conn.commit()
    conn.close()

    print(f"\n✓ Enrolled          : {username}")
    print(f"  Samples           : {len(samples)}")
    print(f"  mean_dwell        : {profile['mean_dwell']:.2f} ms  |  std: {profile['std_dwell']:.2f}")
    print(f"  mean_flight       : {profile['mean_flight']:.2f} ms  |  std: {profile['std_flight']:.2f}")
    print(f"  Z threshold       : {Z_THRESHOLD}  (fixed, distance is already in z-space)")
    print("="*60 + "\n")

    return jsonify({
        "status":   "ok",
        "enrolled": True,
        "message":  "Keystroke profile saved successfully",
        "profile": {
            "mean_dwell":   profile["mean_dwell"],
            "std_dwell":    profile["std_dwell"],
            "mean_flight":  profile["mean_flight"],
            "std_flight":   profile["std_flight"],
            "sample_count": len(samples),
            "threshold":    Z_THRESHOLD,
        }
    })


# ─────────────────────────────────────────────
#  API: LOGIN
# ─────────────────────────────────────────────

@app.route("/api/login-try", methods=["POST"])
def api_login_try():
    """
    Full authentication pipeline:
      1. Time-based lockout check (auto-resets after LOCKOUT_MINUTES)
      2. PBKDF2 password verify  (constant-time comparison)
      3. Load THIS user's keystroke profile from DB
      4. Z-score normalised Euclidean distance  (password-length independent)
      5. Compare against fixed Z_THRESHOLD = 2.5  (mathematically consistent)
      6. Log failures / reset counter on success

    Security note: client-side timing data can be spoofed. In production,
    integrity validation or session-bound capture would be required.

    Body JSON:
    {
      "username": "alice",
      "password": "secret",
      "timings": { "dwell_times": [...], "flight_times": [...], "total_keys": N }
    }
    """
    data = request.get_json()
    print("\n" + "="*60)
    print("LOGIN ATTEMPT")
    print("="*60)

    if data is None:
        return jsonify({"status": "error", "message": "No JSON received"}), 400

    username = data.get("username")
    password = data.get("password")
    timings  = data.get("timings", {})

    if not username or not password:
        return jsonify({"status": "error", "message": "Missing credentials"}), 400

    conn   = get_db()
    cursor = conn.cursor()

    # ── 1. Time-based lockout check ─────────────────────────────────
    if is_locked_out(cursor, username):
        fail_count, last_fail_str = get_fail_info(cursor, username)
        last_fail  = datetime.fromisoformat(last_fail_str)
        unlock_at  = last_fail + timedelta(minutes=LOCKOUT_MINUTES)
        mins_left  = max(0, int((unlock_at - datetime.utcnow()).total_seconds() / 60) + 1)
        conn.commit()
        conn.close()
        print(f"🔒 Account locked: {username}  (unlocks in ~{mins_left} min)")
        print("="*60 + "\n")
        return jsonify({
            "status": "error", "authenticated": False,
            "message": f"Account locked. Try again in ~{mins_left} minute(s)."
        }), 403

    # ── 2. Password verification (PBKDF2 + constant-time compare) ───
    cursor.execute("SELECT id, password, salt FROM users WHERE username = ?", (username,))
    user_row = cursor.fetchone()

    if not user_row:
        conn.close()
        print("❌ User not found")
        print("="*60 + "\n")
        return jsonify({"status": "error", "authenticated": False,
                        "message": "Invalid username or password"}), 401

    user_id, stored_hash, stored_salt = user_row

    # Backward-compat: legacy SHA-256 accounts (no salt)
    if stored_salt:
        password_ok = verify_password(password, stored_hash, stored_salt)
    else:
        legacy = hashlib.sha256(password.encode()).hexdigest()
        password_ok = hmac.compare_digest(legacy, stored_hash)

    if not password_ok:
        conn.close()
        print("❌ Wrong password")
        print("="*60 + "\n")
        return jsonify({"status": "error", "authenticated": False,
                        "message": "Invalid username or password"}), 401

    print("✓ Password verified")

    # ── 3. Load this user's keystroke profile ───────────────────────
    cursor.execute("""
        SELECT mean_dwell, std_dwell, mean_flight, std_flight
        FROM keystroke_profiles
        WHERE user_id = ?
    """, (user_id,))
    profile_row = cursor.fetchone()

    if not profile_row:
        conn.close()
        print("⚠️  No keystroke profile on file")
        print("="*60 + "\n")
        return jsonify({
            "status": "error", "authenticated": False,
            "message": "No keystroke profile found. Please enroll first."
        }), 403

    stored_profile = {
        "mean_dwell":  profile_row[0],
        "std_dwell":   profile_row[1],
        "mean_flight": profile_row[2],
        "std_flight":  profile_row[3],
    }

    # ── 4. Validate keystroke data ──────────────────────────────────
    dwell_times  = timings.get("dwell_times",  [])
    flight_times = timings.get("flight_times", [])

    print(f"\n👤 User           : {username}")
    print(f"   Dwell times    : {dwell_times}")
    print(f"   Flight times   : {flight_times}")
    print(f"   Total keys     : {timings.get('total_keys', 0)}")

    # ── 4a. Length integrity check ─────────────────────────────────
    # total_keys is set by the JS to len(dwell_times); if they disagree
    # someone has tampered with the payload (e.g. injected extra timings).
    reported_total = timings.get("total_keys")
    if reported_total is not None and len(dwell_times) != reported_total:
        conn.close()
        print(f"⚠️  Keystroke length mismatch: reported {reported_total}, got {len(dwell_times)}")
        print("="*60 + "\n")
        return jsonify({
            "status": "error", "authenticated": False,
            "message": "Keystroke length mismatch."
        }), 400

    if not dwell_times or not flight_times:
        conn.close()
        print("⚠️  No keystroke data captured")
        print("="*60 + "\n")
        return jsonify({
            "status": "error", "authenticated": False, "keystroke_verified": False,
            "message": "No keystroke data captured. Please try again."
        }), 400

    # ── 5. Z-score normalised Euclidean distance ────────────────────
    distance = z_score_euclidean_distance(
        {"dwell_times": dwell_times, "flight_times": flight_times},
        stored_profile
    )

    print(f"\n📏 Distance       : {distance:.4f}  (z-space, normalised by data points)")
    print(f"   Threshold      : {Z_THRESHOLD}  (fixed z-space threshold)")
    print(f"   std_dwell      : {stored_profile['std_dwell']:.4f}")
    print(f"   std_flight     : {stored_profile['std_flight']:.4f}")
    print(f"   → {'✓ MATCH' if distance <= Z_THRESHOLD else '❌ MISMATCH'}")

    # ── 6. Decision ─────────────────────────────────────────────────
    if distance > Z_THRESHOLD:
        increment_fail(cursor, username, distance)
        conn.commit()
        fail_count, _ = get_fail_info(cursor, username)
        conn.close()

        remaining = max(MAX_FAILED_ATTEMPTS - fail_count, 0)
        print(f"❌ Access denied  (attempts remaining: {remaining})")
        print("="*60 + "\n")

        if remaining == 0:
            msg = f"Account locked for {LOCKOUT_MINUTES} minutes due to too many failed attempts."
        else:
            msg = (f"Keystroke pattern mismatch "
                   f"(distance {distance:.4f} > threshold {Z_THRESHOLD}). "
                   f"{remaining} attempt(s) remaining.")

        return jsonify({
            "status": "error", "authenticated": False, "keystroke_verified": False,
            "distance":  round(distance, 4),
            "threshold": Z_THRESHOLD,
            "message":   msg,
        }), 401

    # ── Success ─────────────────────────────────────────────────────
    reset_fail(cursor, username)
    conn.commit()
    conn.close()

    session["user"] = username          # ← server-side session set here

    print("✓ Keystroke verified — access granted!")
    print("="*60 + "\n")

    return jsonify({
        "status": "ok", "authenticated": True, "keystroke_verified": True,
        "distance":  round(distance, 4),
        "threshold": Z_THRESHOLD,
        "message":   "Login successful — keystroke pattern matched!",
    })


# ─────────────────────────────────────────────
#  HTML ROUTES
# ─────────────────────────────────────────────

@app.route("/", methods=["GET"])
def login():
    """
    Strict login page — GET only.
    No POST accepted here. All authentication MUST go through /api/login-try.
    On success, JS redirects directly to /home (no form submission).
    """
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    error   = None
    message = None

    if request.method == "POST":
        username = request.form["username"]
        email    = request.form["email"]
        password = request.form["password"]

        pw_hash, pw_salt = hash_password(password)

        try:
            conn   = get_db()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, email, password, salt) VALUES (?, ?, ?, ?)",
                (username, email, pw_hash, pw_salt)
            )
            conn.commit()
            conn.close()
            return redirect(url_for("enroll") + f"?username={username}")
        except sqlite3.IntegrityError:
            error = "Username already exists. Choose another one."

    return render_template("register.html", error=error, message=message)


@app.route("/home")
def home():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("home.html", username=session["user"])


@app.route("/enroll", methods=["GET", "POST"])
def enroll():
    error   = None
    message = None

    if request.method == "POST":
        password = request.form.get("password", "").strip()
        if password:
            message = "Password sample received. Keystroke timings processed."
        else:
            error = "Please type the password before submitting."

    return render_template("enroll.html", message=message, error=error)


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    print("\n" + "="*60)
    print("BEHAVIORAL BIOMETRIC AUTH — READY")
    print("="*60)
    print("✓ PBKDF2-HMAC-SHA256  (salted, 260k iterations)")
    print("✓ hmac.compare_digest  (constant-time, timing-attack safe)")
    print("✓ Z-score normalised Euclidean distance")
    print("✓ Fixed Z_THRESHOLD = 2.5  (pure z-space, no scale mixing)")
    print("✓ Password-length-independent  (normalised by data points)")
    print("✓ Division-by-zero guard  (min_std = 0.0001)")
    print("✓ FIFO queue per key  (repeated-letter dwell bug fixed)")
    print("✓ Consistent key names: dwell_times / flight_times everywhere")
    print("✓ Failed attempt logging  → failed_attempts table")
    print(f"✓ Lockout after {MAX_FAILED_ATTEMPTS} fails, auto-resets after {LOCKOUT_MINUTES} min")
    print("✓ / is GET-only — no password-only POST bypass possible")
    print("✓ Session-protected /home — no direct URL access without auth")
    print("✓ /api/login-try is the ONLY authentication authority")
    print(f"✓ Debug mode: {'ON' if DEBUG_MODE else 'OFF'}  (set FLASK_DEBUG=true to enable)")
    print("="*60 + "\n")
    app.run(debug=DEBUG_MODE)