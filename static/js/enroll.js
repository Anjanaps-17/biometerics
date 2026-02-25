// enroll.js - Captures keystroke dynamics during enrollment
console.log("enroll.js loaded");

(function () {
    const passwordField = document.getElementById('enroll-password');
    if (!passwordField) {
        console.error("Enrollment password field not found!");
        return;
    }

    let enrollmentSamples = [];
    let sampleCount       = 0;
    const REQUIRED_SAMPLES = 3;

    // Per-sample state
    let currentEvents   = [];
    let currentKeyTimes = {}; // key → [] FIFO queue

    // ── Status display ───────────────────────────────────────────────
    function updateStatus(message, isError = false) {
        let el = document.getElementById('enroll-status');
        if (!el) {
            el = document.createElement('div');
            el.id = 'enroll-status';
            el.style.cssText = [
                'margin:15px auto', 'padding:12px', 'border-radius:5px',
                'max-width:400px', 'font-size:14px', 'font-weight:bold'
            ].join(';');
            passwordField.parentElement.insertBefore(el, passwordField.nextSibling);
        }
        el.textContent = message;
        el.style.background = isError ? 'rgba(239,68,68,0.2)'  : 'rgba(34,197,94,0.2)';
        el.style.color      = isError ? '#f87171'               : '#22c55e';
    }

    updateStatus(`Sample 1 of ${REQUIRED_SAMPLES} — type your password`);

    // ── Keystroke capture ────────────────────────────────────────────
    passwordField.addEventListener('keydown', function (e) {
        const key = e.key;
        if (key.length > 1 && key !== 'Backspace' && key !== 'Enter') return;

        // FIX: FIFO queue per key — handles repeated letters safely
        if (!currentKeyTimes[key]) currentKeyTimes[key] = [];
        currentKeyTimes[key].push(e.timeStamp);

        currentEvents.push({ key, type: 'keydown', timestamp: e.timeStamp });
    });

    passwordField.addEventListener('keyup', function (e) {
        const key = e.key;
        if (key.length > 1 && key !== 'Backspace' && key !== 'Enter') return;

        const keyUpTime = e.timeStamp;
        const queue = currentKeyTimes[key];

        if (queue && queue.length > 0) {
            // FIX: consume earliest keydown (FIFO)
            const keyDownTime = queue.shift();
            currentEvents.push({
                key,
                type: 'keyup',
                timestamp: keyUpTime,
                dwell_time: keyUpTime - keyDownTime
            });
        }
    });

    // Clear when field is emptied manually
    passwordField.addEventListener('input', function () {
        if (this.value === '') {
            currentEvents   = [];
            currentKeyTimes = {};
        }
    });

    // ── Form submit ──────────────────────────────────────────────────
    const form = passwordField.closest('form');
    if (!form) return;

    form.addEventListener('submit', function (e) {
        e.preventDefault(); // always — JS handles everything

        const password = passwordField.value;

        if (!password) {
            updateStatus('Please type your password first.', true);
            return;
        }
        if (currentEvents.length === 0) {
            updateStatus('No keystroke data captured. Please type again.', true);
            return;
        }

        // FIX: build the sample in the exact shape the backend expects:
        // { timings: { dwell_times: [...], flight_times: [...] } }
        const timings = extractTimingFeatures(currentEvents);

        enrollmentSamples.push({
            timings: {
                dwell_times:  timings.dwell_times,
                flight_times: timings.flight_times
            }
        });

        sampleCount++;
        console.log(`Sample ${sampleCount} captured:`, timings);

        // Tell the page to update the progress dots
        document.dispatchEvent(new CustomEvent('enrollSampleCaptured', { detail: { count: sampleCount } }));

        if (sampleCount >= REQUIRED_SAMPLES) {
            sendEnrollmentData(enrollmentSamples);
        } else {
            // Reset for next sample
            currentEvents   = [];
            currentKeyTimes = {};
            passwordField.value = '';
            updateStatus(`Sample ${sampleCount + 1} of ${REQUIRED_SAMPLES} — type the same password again`);
            passwordField.focus();
        }
    });

    // ── Send to backend ──────────────────────────────────────────────
    function sendEnrollmentData(samples) {
        updateStatus('Saving your keystroke profile…');

        // FIX: get username from URL param only — no prompt() fallback needed
        // because register always redirects to /enroll?username=...
        const username = new URLSearchParams(window.location.search).get('username');

        if (!username) {
            updateStatus('Username missing from URL. Please re-register.', true);
            return;
        }

        fetch('/api/enroll', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, samples })
        })
        .then(r => r.json())
        .then(data => {
            console.log("Enrollment response:", data);
            if (data.enrolled) {
                updateStatus('✓ Enrollment complete! Redirecting to login…');
                setTimeout(() => {
                    window.location.href = '/';   // send to login page
                }, 2000);
            } else {
                updateStatus(data.message || 'Enrollment failed. Please try again.', true);
                resetEnrollment();
            }
        })
        .catch(err => {
            console.error('Enrollment error:', err);
            updateStatus('Network error during enrollment. Please try again.', true);
            resetEnrollment();
        });
    }

    function resetEnrollment() {
        enrollmentSamples = [];
        currentEvents     = [];
        currentKeyTimes   = {};
        sampleCount       = 0;
        passwordField.value = '';
        updateStatus(`Sample 1 of ${REQUIRED_SAMPLES} — type your password`);
    }

    // ── Timing extractor ─────────────────────────────────────────────
    function extractTimingFeatures(events) {
        const dwellTimes  = [];
        const flightTimes = [];
        let lastKeyUpTime = null;

        for (const event of events) {
            if (event.type === 'keyup' && event.dwell_time != null) {
                dwellTimes.push(event.dwell_time);
            }
            if (event.type === 'keydown' && lastKeyUpTime !== null) {
                flightTimes.push(event.timestamp - lastKeyUpTime);
            }
            if (event.type === 'keyup') {
                lastKeyUpTime = event.timestamp;
            }
        }

        return { dwell_times: dwellTimes, flight_times: flightTimes };
    }

})();