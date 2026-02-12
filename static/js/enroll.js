// enroll.js - Captures keystroke dynamics during enrollment
console.log("enroll.js loaded");

(function() {
    const passwordField = document.getElementById('enroll-password');
    if (!passwordField) {
        console.error("Enrollment password field not found!");
        return;
    }

    // Track enrollment samples
    let enrollmentSamples = [];
    let currentSample = {
        events: [],
        keyDownTimes: {}
    };
    let sampleCount = 0;
    const REQUIRED_SAMPLES = 3;

    // Display status to user
    function updateStatus(message, isError = false) {
        let statusDiv = document.getElementById('enroll-status');
        if (!statusDiv) {
            statusDiv = document.createElement('div');
            statusDiv.id = 'enroll-status';
            statusDiv.style.cssText = `
                margin: 15px auto;
                padding: 12px;
                border-radius: 5px;
                max-width: 400px;
                font-size: 14px;
                font-weight: bold;
            `;
            passwordField.parentElement.insertBefore(statusDiv, passwordField.nextSibling);
        }
        
        statusDiv.textContent = message;
        statusDiv.style.background = isError ? 'rgba(239, 68, 68, 0.2)' : 'rgba(34, 197, 94, 0.2)';
        statusDiv.style.color = isError ? '#f87171' : '#22c55e';
    }

    updateStatus(`Sample ${sampleCount + 1} of ${REQUIRED_SAMPLES} - Start typing your password`);

    // Capture keydown event
    passwordField.addEventListener('keydown', function(e) {
        const key = e.key;
        
        // Ignore special keys
        if (key.length > 1 && key !== 'Backspace' && key !== 'Enter') {
            return;
        }

        // Record keydown time
        if (!currentSample.keyDownTimes[key]) {
            currentSample.keyDownTimes[key] = e.timeStamp;
            
            currentSample.events.push({
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
        const keyDownTime = currentSample.keyDownTimes[key];

        if (keyDownTime) {
            const dwellTime = keyUpTime - keyDownTime;
            
            currentSample.events.push({
                key: key,
                type: 'keyup',
                timestamp: keyUpTime,
                dwell_time: dwellTime
            });

            // Clear the keydown time
            delete currentSample.keyDownTimes[key];
        }
    });

    // Intercept form submission
    const form = passwordField.closest('form');
    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const password = passwordField.value;
            
            if (!password) {
                updateStatus('Please type your password', true);
                return;
            }

            if (currentSample.events.length === 0) {
                updateStatus('No keystroke data captured. Please type again.', true);
                return;
            }

            // Calculate timing features for this sample
            const timingFeatures = extractTimingFeatures(currentSample.events);
            
            // Store this sample
            enrollmentSamples.push({
                password: password,
                events: currentSample.events,
                timings: timingFeatures,
                sample_number: sampleCount + 1
            });

            sampleCount++;
            console.log(`Sample ${sampleCount} captured:`, timingFeatures);

            // Check if we have enough samples
            if (sampleCount >= REQUIRED_SAMPLES) {
                // Send all samples to server
                sendEnrollmentData(enrollmentSamples);
            } else {
                // Clear for next sample
                currentSample = {
                    events: [],
                    keyDownTimes: {}
                };
                passwordField.value = '';
                updateStatus(`Sample ${sampleCount + 1} of ${REQUIRED_SAMPLES} - Type the same password again`);
                passwordField.focus();
            }
        });
    }

    // Send enrollment data to backend
    function sendEnrollmentData(samples) {
        updateStatus('Processing enrollment data...');
        
        // Get username from session/URL or prompt
        const username = new URLSearchParams(window.location.search).get('username') 
                        || prompt('Enter your username for enrollment:');
        
        if (!username) {
            updateStatus('Username required for enrollment', true);
            return;
        }

        fetch('/api/enroll', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                username: username,
                samples: samples,
                sample_count: samples.length
            })
        })
        .then(response => response.json())
        .then(data => {
            console.log("Enrollment response:", data);
            
            if (data.status === 'ok' || data.enrolled) {
                updateStatus('✓ Enrollment successful! Your keystroke pattern has been saved.');
                
                // Redirect to home or login after 2 seconds
                setTimeout(() => {
                    window.location.href = '/home?username=' + encodeURIComponent(username);
                }, 2000);
            } else {
                updateStatus(data.message || 'Enrollment failed. Please try again.', true);
                // Reset enrollment
                resetEnrollment();
            }
        })
        .catch(error => {
            console.error('Error sending enrollment data:', error);
            updateStatus('Error during enrollment. Please try again.', true);
            resetEnrollment();
        });
    }

    // Reset enrollment process
    function resetEnrollment() {
        enrollmentSamples = [];
        currentSample = {
            events: [],
            keyDownTimes: {}
        };
        sampleCount = 0;
        passwordField.value = '';
        updateStatus(`Sample 1 of ${REQUIRED_SAMPLES} - Start typing your password`);
    }

    // Extract timing features
    function extractTimingFeatures(events) {
        const dwellTimes = [];
        const flightTimes = [];
        
        let lastKeyUpTime = null;

        for (let i = 0; i < events.length; i++) {
            const event = events[i];
            
            // Dwell time
            if (event.type === 'keyup' && event.dwell_time) {
                dwellTimes.push(event.dwell_time);
            }
            
            // Flight time
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
            total_keys: dwellTimes.length,
            avg_dwell: dwellTimes.length > 0 ? dwellTimes.reduce((a,b) => a+b, 0) / dwellTimes.length : 0,
            avg_flight: flightTimes.length > 0 ? flightTimes.reduce((a,b) => a+b, 0) / flightTimes.length : 0
        };
    }

    // Clear events when password field is cleared manually
    passwordField.addEventListener('input', function() {
        if (this.value === '') {
            currentSample = {
                events: [],
                keyDownTimes: {}
            };
        }
    });

})();