import undetected_chromedriver as uc
from xvfbwrapper import Xvfb
import time
import os
import json
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

class MicrosoftNotLoggedIn(Exception):
    """Custom exception raised when Microsoft SSO login is required but not expected."""
    pass

class UnileverLogin:
    def __init__(self, headless=True, sap_user="R41B862", sap_pass="Lakme$$2026"):
        self.vdisplay = None
        self.driver = None
        self.sap_user = sap_user
        self.sap_pass = sap_pass
        
        if headless:
            self.vdisplay = Xvfb(width=1920, height=1080, colordepth=24)
            self.vdisplay.start()
            print("Virtual display started...")

        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        
        profile_path = os.path.abspath("./chrome_profile")
        print(f"Using Chrome profile at: {profile_path}")
        options.add_argument(f"--user-data-dir={profile_path}")

        self.driver = uc.Chrome(options=options)
        print("Browser launched.")
        
        self.wait = WebDriverWait(self.driver, 15)
        self.short_wait = WebDriverWait(self.driver, 5)

    def close(self):
        """Clean up the browser and virtual display."""
        print("\nCleaning up resources...")
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass
        if self.vdisplay:
            self.vdisplay.stop()

    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _wait_and_click(self, wait, by, selector, desc="element", screenshot_name=None):
        try:
            element = wait.until(EC.element_to_be_clickable((by, selector)))
            try:
                element.click()
            except:
                self.driver.execute_script("arguments[0].click();", element)
            print(f"Clicked {desc}.")
            if screenshot_name:
                time.sleep(1)
                self.driver.save_screenshot(screenshot_name)
            return True
        except Exception:
            print(f"Could not click {desc}. (Selector: {selector})")
            if screenshot_name:
                self.driver.save_screenshot(f"error_{screenshot_name}")
            return False

    def _wait_and_send_keys(self, wait, by, selector, keys, desc="input", screenshot_name=None):
        try:
            element = wait.until(EC.presence_of_element_located((by, selector)))
            ActionChains(self.driver).move_to_element(element).click().perform()
            element.clear()
            element.send_keys(keys)
            print(f"Entered text into {desc}.")
            if screenshot_name:
                time.sleep(1)
                self.driver.save_screenshot(screenshot_name)
            return element
        except Exception:
            print(f"Could not enter text into {desc}. (Selector: {selector})")
            if screenshot_name:
                self.driver.save_screenshot(f"error_{screenshot_name}")
            return None



    def _check_if_ms_login_required(self):
        url = "https://web3.inpartner.unilever.com/sap/bc/ui5_ui5/sap/zpmodel/index.html"
        print(f"Navigating to {url}")
        self.driver.get(url)
        time.sleep(5)
        self.driver.save_screenshot("step0_initial_load.png")

        needs_ms_login = False
        current_url = self.driver.current_url.lower()
        email_css = "input[type='email'], input[name='loginfmt'], input[name='email']"
        
        if "microsoftonline" in current_url:
            needs_ms_login = True
        else:
            try:
                self.short_wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, email_css)))
                needs_ms_login = True
            except:
                pass
        
        return needs_ms_login

    def _execute_sap_login(self):
        print("\n--- Starting Unilever SAP Login ---")
        time.sleep(5)
        self.driver.save_screenshot("sap_login_start.png")

        sap_user_css = "input[name='sap-user'], input[id*='USERNAME_FIELD'], input[type='text']"
        self._wait_and_send_keys(self.wait, By.CSS_SELECTOR, sap_user_css, self.sap_user, "SAP Username")

        sap_pass_css = "input[name='sap-password'], input[id*='PASSWORD_FIELD'], input[type='password']"
        self._wait_and_send_keys(self.wait, By.CSS_SELECTOR, sap_pass_css, self.sap_pass, "SAP Password")

        sap_login_btn_css = "button#LOGIN_LINK, button[onclick*='submitLogin'], button.sapMBtnEmphasized, button[type='submit']"
        self._wait_and_click(self.wait, By.CSS_SELECTOR, sap_login_btn_css, "SAP Login button")
        
        time.sleep(8)
        self.driver.save_screenshot("sap_post_login_dashboard.png")
        print("Finished SAP login process.")
        
        return self.driver.get_cookies()

    def get_sap_cookies(self):
        """
        Highest level method to trigger the login flow and return cookies.
        """
        try:
            if self._check_if_ms_login_required():
                # We can't do interactive OTP in a background worker easy.
                # But for the sake of the worker, let's just use the sap_only flow.
                # If it raises MicrosoftNotLoggedIn, the worker will handle the error.
                raise MicrosoftNotLoggedIn("Microsoft SSO login screen detected.")
            
            return self._execute_sap_login()
        except Exception as e:
            print(f"Error in get_sap_cookies: {e}")
            raise e

    def login_sap_only(self):
        """
        Fast-path login. Assumes Microsoft SSO is already authenticated via cookies.
        Raises MicrosoftNotLoggedIn if the SSO portal intercepts the request.
        Requires NO interactive user input.
        """
        try:
            if self._check_if_ms_login_required():
                raise MicrosoftNotLoggedIn("Microsoft SSO login screen detected. Call login_with_ms_sso() instead.")
            
            self._execute_sap_login()

        except MicrosoftNotLoggedIn as e:
            raise e
        except Exception as e:
            print(f"An unexpected error occurred in SAP-only flow: {e}")
            try:
                self.driver.save_screenshot("fatal_error_sap.png")
            except: pass

    def login_with_ms_sso(self):
        """
        Superset login. Handles interactive Microsoft SSO first if required, then progresses to SAP login.
        """
        try:
            if self._check_if_ms_login_required():
                print("\n--- Starting Microsoft SSO Login ---")
                email_css = "input[type='email'], input[name='loginfmt'], input[name='email']"
                submit_css = "input[type='submit'], button[type='submit']"

                # 4. Enter Email
                email_field = self._wait_and_send_keys(self.wait, By.CSS_SELECTOR, email_css, "devakilever@gmail.com", "email field", "step1_email_entered.png")
                if email_field:
                    self._wait_and_click(self.wait, By.CSS_SELECTOR, submit_css, "Next button")

                # 5. Click 'Other ways to sign in'
                print("Waiting for 'Other ways to sign in'...")
                time.sleep(3)
                other_ways_xpath = "//*[contains(text(), 'Other ways to sign in')]"
                self._wait_and_click(self.wait, By.XPATH, other_ways_xpath, "'Other ways to sign in'", "step2_before_other_ways.png")

                # 6. Click 'Password' option
                print("Waiting for 'Password' option...")
                time.sleep(2)
                pass_opt_css = "div[aria-label='Use your password'], div.tile-container"
                self._wait_and_click(self.wait, By.CSS_SELECTOR, pass_opt_css, "'Password' option", "step3_before_password_option.png")

                # 7. Enter Password
                print("Waiting for password input...")
                time.sleep(2)
                pass_input_css = "input[type='password'], input[name='passwd'], input[name='password']"
                pass_field = self._wait_and_send_keys(self.wait, By.CSS_SELECTOR, pass_input_css, "Ven2004@", "password field", "step4_password_entered.png")
                if pass_field:
                    self._wait_and_click(self.wait, By.CSS_SELECTOR, submit_css, "Sign in button")

                # 8. Stay signed in (Yes)
                print("Waiting for 'Stay signed in' prompt...")
                time.sleep(1)
                yes_xpath = "//input[@type='submit' and @value='Yes'] | //button[@type='submit' and contains(text(), 'Yes')] | //*[contains(translate(text(), 'YES', 'yes'), 'yes')]"
                self._wait_and_click(self.wait, By.XPATH, yes_xpath, "'Yes' (Stay signed in)", "step5_stay_signed_in.png")

                # 9. Handle OTP
                print("Waiting for OTP options...")
                time.sleep(5)
                self.driver.save_screenshot("step6_otp_options.png")

                print("Attempting to select the SMS/Text option...")
                sms_css = "div[data-value='OneWaySMS'], [role='button'][data-value*='SMS'], #idDiv_SAOTCS_Proofs [role='button']"
                sms_xpath = "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'text ') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'sms')]"
                
                if not self._wait_and_click(self.short_wait, By.CSS_SELECTOR, sms_css, "SMS option (CSS)"):
                    self._wait_and_click(self.short_wait, By.XPATH, sms_xpath, "SMS option (XPath)")

                # Wait for interactive prompt from the terminal/console
                time.sleep(2)
                otp_css = "input[type='tel'], input[name='otc'], input[id='idTxtBx_SAOTCC_OTC']"
                try:
                    self.short_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, otp_css)))
                    self.driver.save_screenshot("step7_otp_input.png")
                    otp_code = input("\n>>> PLEASE ENTER THE SMS OTP RECEIVED: ").strip()
                    
                    if self._wait_and_send_keys(self.wait, By.CSS_SELECTOR, otp_css, otp_code, "OTP field"):
                        self._wait_and_click(self.wait, By.CSS_SELECTOR, submit_css, "Verify/Next after OTP")
                        time.sleep(5)
                        self.driver.save_screenshot("step8_after_otp.png")
                        print("Finished OTP process.")
                except:
                    print("OTP field not found. Skipping interactive prompt.")

                print("Waiting briefly for redirect back to SAP portal...")
                time.sleep(5)
            else:
                print("\n--- Skipped Microsoft SSO Login (Already authenticated) ---")

            self._execute_sap_login()

        except Exception as e:
            print(f"An unexpected error occurred in SSO flow: {e}")
            try:
                self.driver.save_screenshot("fatal_error_sso.png")
            except: pass

if __name__ == "__main__":
    # Example usage using context manager for automatic cleanup
    with UnileverLogin() as bot:
        try:
            print("Attempting fast SAP login (Background)...")
            bot.login_sap_only()
        except MicrosoftNotLoggedIn as e:
            print(f"Exception Caught: {e}")
            print("Falling back to interactive MS SSO Login...")
            bot.login_with_ms_sso()
