import undetected_chromedriver as uc
from xvfbwrapper import Xvfb
import time
import random
import os
from datetime import datetime, timedelta

# Global list to track timestamps of recent token requests
_REQUEST_HISTORY = []

# Multi-tiered rate limits: (max_requests, window_minutes)
RATE_LIMITS = [
    (10, 20),      # Tier 1: 10 requests / 20 minutes
    (15, 60),      # Tier 2: 15 requests / 1 hour
    (20, 360)      # Tier 3: 20 requests / 6 hours
]

def get_enterprise_token():
    """
    Generates a reCAPTCHA Enterprise token for IKEA.
    Implements a multi-tiered rate limit for robustness.
    """
    global _REQUEST_HISTORY
    
    # 0. Rate Limit Check
    now = datetime.now()
    
    # Prune history: keep only timestamps within the longest window (6 hours)
    max_window_minutes = max(limit[1] for limit in RATE_LIMITS)
    cutoff = now - timedelta(minutes=max_window_minutes)
    _REQUEST_HISTORY = [t for t in _REQUEST_HISTORY if t > cutoff]
    
    # Check each tier
    for max_reqs, window_mins in RATE_LIMITS:
        window_start = now - timedelta(minutes=window_mins)
        # Count requests in this specific window
        count = sum(1 for t in _REQUEST_HISTORY if t > window_start)
        
        if count >= max_reqs:
            # We hit this limit. Find the oldest request in this window to calculate wait time.
            requests_in_window = [t for t in _REQUEST_HISTORY if t > window_start]
            requests_in_window.sort()
            first_in_window = requests_in_window[0]
            
            wait_time = (first_in_window + timedelta(minutes=window_mins)) - now
            seconds_to_wait = int(wait_time.total_seconds())
            
            # Use units that make sense (mins if >= 60s, else secs)
            if seconds_to_wait >= 60:
                wait_desc = f"{seconds_to_wait // 60} minutes"
            else:
                wait_desc = f"{seconds_to_wait} seconds"
                
            return f"Error: Rate limit exceeded ({max_reqs} reqs / {window_mins} mins). Please wait {wait_desc}."

    # Record the current request
    _REQUEST_HISTORY.append(now)

    # 1. Start Virtual Display (This is the 'magic' for Linux servers)
    vdisplay = Xvfb(width=1920, height=1080, colordepth=24)
    vdisplay.start()
    print("Virtual display started...")

    try:
        # 2. Configure Undetected Chromedriver
        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        
        # We DO NOT use --headless because Xvfb handles the display.
        # This makes Google think we are a real desktop user.
        print("Launch Browser")
        driver = uc.Chrome(options=options,version_main=145)
        print("Browser launched in virtual display.")

        # 3. Navigate to the page
        url = "https://leveredge57.hulcd.com/rsunify/"
        driver.get(url)
        
        # 4. Human Simulation (Warming up the reCAPTCHA engine)
        time.sleep(random.uniform(4, 6))
        # Small random scroll
        driver.execute_script(f"window.scrollBy(0, {random.randint(300, 700)});")
        time.sleep(2)
        print("Simulated human activity...")

        # 5. Execute the reCAPTCHA Enterprise script
        # The key 6LeEnj... is the SiteKey from your page source
        script = """
        var callback = arguments[arguments.length - 1];
        if (typeof grecaptcha === 'undefined' || typeof grecaptcha.enterprise === 'undefined') {
            callback("Error: Library not loaded");
        } else {
            grecaptcha.enterprise.ready(function () {
                grecaptcha.enterprise.execute('6LeEnjQsAAAAAA4La1SFIN31abdvhqeSCmeI03kX', { action: 'login' })
                    .then(function (token) {
                        callback(token);
                    })
                    .catch(function (err) {
                        callback("Error: " + err);
                    });
            });
        }
        """
        
        print("Requesting token from Google...")
        token = driver.execute_async_script(script)
        return token

    except Exception as e:
        return f"An error occurred: {e}"

    finally:
        # 6. Cleanup (CRITICAL: if you don't stop Xvfb, your server memory will fill up)
        print("Cleaning up resources...")
        try:
            driver.quit()
        except:
            pass
        vdisplay.stop()

if __name__ == "__main__":
    token = get_enterprise_token()
    if token and "Error" not in token:
        print("\n" + "="*50)
        print("SUCCESS! VALID TOKEN GENERATED:")
        print(token)
        print("="*50 + "\n")
    else:
        print(f"Failed to get token: {token}")