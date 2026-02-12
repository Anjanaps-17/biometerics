// login.js - Captures keystroke dynamics during login
console.log("login.js loaded");

(function() {
    const passwordField = document.getElementById('password');
    if (!passwordField) {
        console.error("Password field not found!");
        return;
    }

    // Store keystroke events
    let keystrokeEvents = [];
    let keyDownTimes = {}; // Track when each key was pressed

    // Capture keydown event
    passwordField.addEventListener('keydown', function(e) {
        const key = e.key;
        
        // Ignore special keys like Shift, Ctrl, Alt, etc.
        if (key.length > 1 && key !== 'Backspace' && key !== 'Enter') {
            return;
        }

        // Record keydown time
        if (!keyDownTimes[key]) {
            keyDownTimes[key] = e.timeStamp;
            
            keystrokeEvents.push({
                key: key,
                type: 'keydown',
                timestamp: e.timeStamp
            });
        }
    });

    // Capture keyup event
    passwordField.addEventListener('keyup', function(e) {
        const key = e.key;
        
        // Ignore special keys
        if (key.length > 1 && key !== 'Backspace' && key !== 'Enter') {
            return;
        }

        const keyUpTime = e.timeStamp;
        const keyDownTime = keyDownTimes[key];

        if (keyDownTime) {
            keystrokeEvents.push({
                key: key,
                type: 'keyup',
                timestamp: keyUpTime,
                dwell_time: keyUpTime - keyDownTime
            });

            // Clear the keydown time
            delete keyDownTimes[key];
        }
    });

    // Intercept form submission to send keystroke data
    const form = passwordField.closest('form');
    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault(); // Prevent default form submission
            
            const username = form.querySelector('input[name="username"]').value;
            const password = form.querySelector('input[name="password"]').value;

            if (!username || !password) {
                alert('Please enter both username and password');
                return;
            }

            // Calculate timing features
            const timingFeatures = extractTimingFeatures(keystrokeEvents);
            
            console.log("Keystroke events captured:", keystrokeEvents.length);
            console.log("Timing features:", timingFeatures);

            // Send keystroke data to backend
            fetch('/api/login-try', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    username: username,
                    password: password,
                    events: keystrokeEvents,
                    timings: timingFeatures
                })
            })
            .then(response => response.json())
            .then(data => {
                console.log("Server response:", data);
                
                // If keystroke verification successful, submit the actual form
                if (data.status === 'ok' || data.authenticated) {
                    // Now submit the form normally
                    form.removeEventListener('submit', arguments.callee);
                    form.submit();
                } else {
                    alert(data.message || 'Authentication failed. Keystroke pattern did not match.');
                }
            })
            .catch(error => {
                console.error('Error sending keystroke data:', error);
                // On error, allow normal login (fallback)
                form.removeEventListener('submit', arguments.callee);
                form.submit();
            });
        });
    }

    // Extract dwell times and flight times
    function extractTimingFeatures(events) {
        const dwellTimes = [];
        const flightTimes = [];
        
        let lastKeyUpTime = null;

        for (let i = 0; i < events.length; i++) {
            const event = events[i];
            
            // Calculate dwell time (keydown to keyup for same key)
            if (event.type === 'keyup' && event.dwell_time) {
                dwellTimes.push(event.dwell_time);
            }
            
            // Calculate flight time (time between consecutive key presses)
            if (event.type === 'keydown') {
                if (lastKeyUpTime !== null) {
                    const flightTime = event.timestamp - lastKeyUpTime;
                    flightTimes.push(flightTime);
                }
            }
            
            if (event.type === 'keyup') {
                lastKeyUpTime = event.timestamp;
            }
        }

        return {
            dwell_times: dwellTimes,
            flight_times: flightTimes,
            total_keys: dwellTimes.length
        };
    }

    // Clear events when password field is cleared
    passwordField.addEventListener('input', function() {
        if (this.value === '') {
            keystrokeEvents = [];
            keyDownTimes = {};
        }
    });

})();