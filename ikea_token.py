import undetected_chromedriver as uc
from xvfbwrapper import Xvfb
import time
import random
import os

def get_enterprise_token():
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
        url = "https://leveredge18.hulcd.com/rsunify/"
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