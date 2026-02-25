// login.js - Captures keystroke dynamics during login
console.log("login.js loaded");

(function () {
    const passwordField = document.getElementById('password');
    if (!passwordField) {
        console.error("Password field not found!");
        return;
    }

    let keystrokeEvents = [];
    // FIX: use a list per key (FIFO queue) so repeated letters don't collide
    let keyDownTimes = {};

    passwordField.addEventListener('keydown', function (e) {
        const key = e.key;
        if (key.length > 1 && key !== 'Backspace' && key !== 'Enter') return;

        // FIX: always push, never overwrite — handles "aa", "ss", etc.
        if (!keyDownTimes[key]) keyDownTimes[key] = [];
        keyDownTimes[key].push(e.timeStamp);

        keystrokeEvents.push({ key, type: 'keydown', timestamp: e.timeStamp });
    });

    passwordField.addEventListener('keyup', function (e) {
        const key = e.key;
        if (key.length > 1 && key !== 'Backspace' && key !== 'Enter') return;

        const keyUpTime = e.timeStamp;
        const queue = keyDownTimes[key];

        if (queue && queue.length > 0) {
            // FIX: pop the EARLIEST keydown for this key (FIFO)
            const keyDownTime = queue.shift();
            keystrokeEvents.push({
                key,
                type: 'keyup',
                timestamp: keyUpTime,
                dwell_time: keyUpTime - keyDownTime
            });
        }
    });

    // Clear when field is emptied
    passwordField.addEventListener('input', function () {
        if (this.value === '') {
            keystrokeEvents = [];
            keyDownTimes = {};
        }
    });

    // Intercept form submission
    const form = passwordField.closest('form');
    if (!form) return;

    form.addEventListener('submit', function handleSubmit(e) {
        e.preventDefault();

        const username = form.querySelector('input[name="username"]').value.trim();
        const password = form.querySelector('input[name="password"]').value;

        if (!username || !password) {
            alert('Please enter both username and password');
            return;
        }

        const timings = extractTimingFeatures(keystrokeEvents);

        console.log("Keystroke events:", keystrokeEvents.length);
        console.log("Timings being sent:", timings);

        fetch('/api/login-try', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, timings })
        })
        .then(r => r.json())
        .then(data => {
            console.log("Server response:", data);
            if (data.authenticated) {
                // FIX: remove listener before submitting so no infinite loop
                form.removeEventListener('submit', handleSubmit);
                form.submit();
            } else {
                alert(data.message || 'Authentication failed. Keystroke pattern did not match.');
                // Reset keystroke data so user can try again cleanly
                keystrokeEvents = [];
                keyDownTimes = {};
            }
        })
        .catch(err => {
            console.error('Network error:', err);
            form.removeEventListener('submit', handleSubmit);
            form.submit(); // fallback: allow login on network error
        });
    });

    function extractTimingFeatures(events) {
        const dwellTimes = [];
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

        return {
            dwell_times:  dwellTimes,
            flight_times: flightTimes,
            total_keys:   dwellTimes.length
        };
    }

})();