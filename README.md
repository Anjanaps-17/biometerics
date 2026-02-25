# 🔐 Behavioral Biometric User Authentication System

A secure web-based login system that authenticates users using **keystroke dynamics** — analysing how a person types their password (not just what they type). Built with Flask, SQLite, and vanilla JavaScript.

---

## 📌 What Is This?

Traditional login systems only verify *what* you know (your password). This system adds a second layer by verifying *how* you type — your unique keystroke rhythm. Even if someone steals your password, login becomes significantly harder without matching the enrolled typing pattern.

This technique is called **Behavioral Biometrics** and is used in real-world systems by banks and cybersecurity firms.

---

## 🧠 How It Works

### Enrollment Phase
1. User registers with username, email, and password
2. User is redirected to the enrollment page
3. User types their password **3 times**
4. The system captures **dwell times** (how long each key is held) and **flight times** (gap between key releases and next key press)
5. Mean and standard deviation are calculated and saved to the database as the user's **keystroke profile**

### Login Phase
1. User enters username and password
2. Password is verified using PBKDF2-HMAC-SHA256
3. Keystroke timings from the login attempt are captured
4. A **Z-score normalised Euclidean distance** is computed between the live timings and the stored profile
5. If the distance is within the threshold → access granted ✅
6. If not → access denied, attempt is logged ❌

---

## 🔬 The Algorithm

### Distance Formula

```
z = (t - mean) / std          ← z-score for each timing
distance = sqrt(Σz²) / N      ← normalised by number of data points
```

- Uses **standard deviation** stored during enrollment — consistent typists face a stricter check, variable typists get proportional tolerance
- Dividing by `N` makes the metric **independent of password length**
- Compared against a **fixed Z-space threshold of 2.5**
- The system assumes approximate normality of timing features for z-score validity

### Why Z-Score?
A raw Euclidean distance would grow with password length and be unfair to users with natural timing variation. Z-score normalisation solves both problems and is the approach used in academic keystroke biometric research.

---

## 🛡️ Security Features

| Feature | Implementation |
|---|---|
| Password hashing | PBKDF2-HMAC-SHA256, random 32-byte salt, 260,000 iterations |
| Timing-safe comparison | `hmac.compare_digest()` prevents timing attacks |
| Keystroke verification | Z-score normalised Euclidean distance |
| Failed attempt logging | Every failed login logged with distance + timestamp |
| Account lockout | Locked after 3 failed attempts, auto-resets after 15 minutes |
| Repeated-key safety | FIFO queue per key prevents dwell corruption on repeated letters |
| Database safety | Parameterised SQL queries (`?` placeholders) prevent SQL injection |

---

## 🗂️ Project Structure

```
myflaskapp/
│
├── app.py                  ← Main Flask application
├── users.db                ← SQLite database (auto-created)
│
├── templates/
│   ├── login.html          ← Login page
│   ├── register.html       ← Registration page
│   ├── enroll.html         ← Keystroke enrollment page
│   └── home.html           ← Home page after login
│
└── static/
    └── js/
        ├── login.js        ← Captures keystrokes during login
        └── enroll.js       ← Captures 3 enrollment samples
```

---

## 🗄️ Database Schema

```sql
users (id, username, email, password, salt)

keystroke_profiles (user_id, mean_dwell, std_dwell, mean_flight, std_flight)

failed_attempts (id, username, distance, timestamp)

lockout (username, fail_count, last_fail_time)
```

---

## ⚙️ Setup & Installation

### Prerequisites
- Python 3.8+
- pip

### Steps

```bash
# 1. Clone or download the project
cd myflaskapp

# 2. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux

# 3. Install dependencies
pip install flask

# 4. Run the app
python app.py
```

Open your browser at: **http://127.0.0.1:5000**

---

## 🚀 Usage Flow

```
Register → Enroll (type password 3×) → Login
```

1. Go to `/register` — create your account
2. You are automatically redirected to `/enroll`
3. Type your password **3 times** — green dots fill as each sample is captured
4. After enrollment, you are redirected to the login page
5. Log in — the system verifies both your password AND your typing pattern

---

## 🔧 Configuration

All tunable parameters are at the top of `app.py`:

```python
MAX_FAILED_ATTEMPTS = 3      # Lockout after this many failures
LOCKOUT_MINUTES     = 15     # Auto-unlock after this many minutes
Z_THRESHOLD         = 2.5    # Authentication threshold (z-space)
MIN_STD             = 0.0001 # Division-by-zero guard
```

To enable debug mode without editing code:
```bash
set FLASK_DEBUG=true         # Windows
export FLASK_DEBUG=true      # Mac/Linux
python app.py
```

---

## 📊 Determining the Threshold

The threshold of **2.5** is chosen as a practical heuristic based on z-score conventions and can be empirically tuned. In a strict normal distribution, values beyond 2.5 standard deviations represent less than 1.2% of genuine samples — however, keystroke timings in practice may be skewed or have heavier tails, and a small enrollment sample of 3 makes standard deviation estimates less reliable. The threshold should therefore be treated as a starting point subject to empirical validation.

In a production system, the threshold would be tuned by:
1. Collecting genuine login distances (same user)
2. Collecting impostor distances (different user, same password)
3. Choosing the threshold that minimises both False Acceptance Rate (FAR) and False Rejection Rate (FRR)

---

## ⚠️ Known Limitations

- **Client-side timing**: Keystroke data is captured in the browser and sent via JSON. A determined attacker could replay or spoof timing values. In production, session-binding or cryptographic signing of timing data would be required.
- **Single device assumption**: Typing patterns vary slightly across keyboards. A user enrolling on a laptop may face higher distances when logging in on a different keyboard.
- **Small enrollment sample**: Only 3 samples are used. More samples produce a more reliable profile.
- **Normality assumption**: Z-score distance assumes approximate normality of timing distributions, which may not hold for all users or keyboards.

---

## 🔮 Future Improvements

- **Server-side keystroke capture** via WebAuthn-style secure channels to prevent timing data spoofing
- **Adaptive threshold per user** using rolling average updates as the user logs in over time
- **Multi-feature modeling** — key-specific timing vectors instead of a single global mean/std per user
- **Machine learning classifier** (SVM or Random Forest) for more accurate genuine vs. impostor separation
- **Migration to PostgreSQL** for production-grade scalability and concurrent access
- **Cross-device normalisation** to account for timing differences between keyboards

---

## 🎓 Academic Context

This project implements concepts from:
- **Keystroke Dynamics** — behavioural biometric modality first studied in the 1980s
- **Z-score normalisation** — standard statistical technique for feature scaling
- **Euclidean distance** — common similarity metric in biometric verification systems

---

## 👤 Author

Developed as a university project on **Behavioral Biometric User Authentication**.
