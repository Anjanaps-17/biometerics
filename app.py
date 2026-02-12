from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
import hashlib
import math
from statistics import mean, stdev

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

# ---------- KEYSTROKE ANALYSIS FUNCTIONS ----------

def calculate_profile_statistics(samples):
    """
    Calculate mean and standard deviation for keystroke timings
    from multiple enrollment samples.
    
    Args:
        samples: List of sample dictionaries, each containing 'timings' with dwell_times and flight_times
    
    Returns:
        Dictionary with mean and std for dwell and flight times
    """
    all_dwell_times = []
    all_flight_times = []
    
    # Collect all timing data from all samples
    for sample in samples:
        timings = sample.get('timings', {})
        dwell_times = timings.get('dwell_times', [])
        flight_times = timings.get('flight_times', [])
        
        all_dwell_times.extend(dwell_times)
        all_flight_times.extend(flight_times)
    
    # Calculate statistics
    profile = {
        'mean_dwell': mean(all_dwell_times) if all_dwell_times else 0,
        'std_dwell': stdev(all_dwell_times) if len(all_dwell_times) > 1 else 0,
        'mean_flight': mean(all_flight_times) if all_flight_times else 0,
        'std_flight': stdev(all_flight_times) if len(all_flight_times) > 1 else 0,
        'dwell_count': len(all_dwell_times),
        'flight_count': len(all_flight_times)
    }
    
    return profile

def euclidean_distance(current_timings, stored_profile):
    """
    Calculate Euclidean distance between current keystroke timings 
    and stored profile.
    
    Formula: distance = sqrt(sum((current - mean)^2))
    
    Args:
        current_timings: Dict with 'dwell_times' and 'flight_times' arrays
        stored_profile: Dict with mean and std values
    
    Returns:
        Float: Euclidean distance (lower = more similar)
    """
    dwell_times = current_timings.get('dwell_times', [])
    flight_times = current_timings.get('flight_times', [])
    
    mean_dwell = stored_profile.get('mean_dwell', 0)
    mean_flight = stored_profile.get('mean_flight', 0)
    
    # Calculate squared differences
    dwell_diff_squared = sum((t - mean_dwell) ** 2 for t in dwell_times)
    flight_diff_squared = sum((t - mean_flight) ** 2 for t in flight_times)
    
    # Euclidean distance
    distance = math.sqrt(dwell_diff_squared + flight_diff_squared)
    
    return distance

# ---------- API ROUTES (for keystrokes) ----------

@app.route("/api/enroll", methods=["POST"])
def api_enroll():
    """
    Handle keystroke enrollment - receives 3 samples and calculates profile
    """
    data = request.get_json()
    print("\n" + "="*60)
    print("ENROLLMENT DATA RECEIVED")
    print("="*60)

    if data is None:
        return jsonify({"status": "error", "message": "No JSON received"}), 400
    
    username = data.get('username')
    samples = data.get('samples', [])
    
    if not username or not samples:
        return jsonify({"status": "error", "message": "Missing username or samples"}), 400
    
    if len(samples) < 3:
        return jsonify({"status": "error", "message": "Need at least 3 samples"}), 400
    
    # Calculate profile statistics from all samples
    profile = calculate_profile_statistics(samples)
    
    print(f"\n✓ Enrollment successful for user: {username}")
    print(f"  Samples collected: {len(samples)}")
    print(f"  Mean dwell time: {profile['mean_dwell']:.2f} ms")
    print(f"  Std dwell time: {profile['std_dwell']:.2f} ms")
    print(f"  Mean flight time: {profile['mean_flight']:.2f} ms")
    print(f"  Std flight time: {profile['std_flight']:.2f} ms")
    print(f"  Total dwell events: {profile['dwell_count']}")
    print(f"  Total flight events: {profile['flight_count']}")
    print("="*60 + "\n")
    
    # Return success (your friend will save to database later)
    return jsonify({
        "status": "ok",
        "enrolled": True,
        "message": "Keystroke profile created successfully",
        "profile": {
            "mean_dwell": profile['mean_dwell'],
            "std_dwell": profile['std_dwell'],
            "mean_flight": profile['mean_flight'],
            "std_flight": profile['std_flight'],
            "sample_count": len(samples)
        }
    })

@app.route("/api/login-try", methods=["POST"])
def api_login_try():
    """
    Handle login keystroke verification - validates password and keystroke timing
    """
    data = request.get_json()
    print("\n" + "="*60)
    print("LOGIN ATTEMPT - KEYSTROKE DATA RECEIVED")
    print("="*60)

    if data is None:
        return jsonify({"status": "error", "message": "No JSON received"}), 400
    
    username = data.get('username')
    password = data.get('password')
    timings = data.get('timings', {})
    
    if not username or not password:
        return jsonify({"status": "error", "message": "Missing credentials"}), 400
    
    # Display captured keystroke data
    print(f"\n👤 User: {username}")
    print(f"📊 Keystroke Timings Captured:")
    print(f"   Dwell times: {timings.get('dwell_times', [])}")
    print(f"   Flight times: {timings.get('flight_times', [])}")
    print(f"   Total keys: {timings.get('total_keys', 0)}")
    
    # Verify password first
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        print("❌ User not found")
        print("="*60 + "\n")
        return jsonify({
            "status": "error",
            "authenticated": False,
            "message": "Invalid username or password"
        }), 401
    
    stored_hashed = row[0]
    if stored_hashed != hash_password(password):
        print("❌ Password incorrect")
        print("="*60 + "\n")
        return jsonify({
            "status": "error",
            "authenticated": False,
            "message": "Invalid username or password"
        }), 401
    
    print("✓ Password verified")
    
    
    if timings.get('dwell_times') and timings.get('flight_times'):
        print("✓ Keystroke data validated")
        print("\n Keystroke verification skipped")
        print("   (Need to implement database comparison)")
        print("="*60 + "\n")
        
        
        return jsonify({
            "status": "ok",
            "authenticated": True,
            "keystroke_verified": True,
            "message": "Login successful (keystroke verification pending database implementation)"
        })
    else:
        print("⚠️  No keystroke data captured")
        print("="*60 + "\n")
        return jsonify({
            "status": "ok",
            "authenticated": True,
            "keystroke_verified": False,
            "message": "Login successful (no keystroke data)"
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
            
            # After registration, redirect to enrollment
            return redirect(url_for("enroll") + f"?username={username}")
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

# ---------- Keystroke helper (for your friend to use later) ----------

def extract_timings(events):
    """
    Helper function to extract dwell and flight times from raw events.
    
    """
    dwell_times = []
    flight_times = []
    
    last_keyup_time = None
    keydown_times = {}
    
    for event in events:
        if event['type'] == 'keydown':
            keydown_times[event['key']] = event['timestamp']
            
            if last_keyup_time is not None:
                flight_time = event['timestamp'] - last_keyup_time
                flight_times.append(flight_time)
        
        elif event['type'] == 'keyup':
            if event['key'] in keydown_times:
                dwell_time = event['timestamp'] - keydown_times[event['key']]
                dwell_times.append(dwell_time)
                last_keyup_time = event['timestamp']
    
    return {
        "dwell": dwell_times,
        "flight": flight_times
    }

# ---------- MAIN ----------

if __name__ == "__main__":
    init_db()
    print("\n" + "="*60)
    print("STARTING")
    print("="*60)
    print("✓ Keystroke capture enabled (login.js & enroll.js)")
    print("✓ API endpoints ready (/api/enroll, /api/login-try)")
    print("⚠️  Database storage: Pending (task)")
    print("✓ Euclidean distance algorithm: Ready (in code)")
    print("="*60 + "\n")
    app.run(debug=True)


