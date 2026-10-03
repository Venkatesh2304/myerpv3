---
name: login
description: Standardized SOP and deterministic debugging guide for service authentication, Playwright IKEA browser automation, GST/eInvoice portal logins, session cookie synchronization, and DOM troubleshooting procedures.
---

# Master Authentication & Login Skill (`login`)

This skill defines the centralized session synchronization architecture, automated Playwright browser login pipelines, direct portal logins (GST & eInvoice), and deterministic debugging procedures when authentication steps encounter external site changes.

---

## 1. System Architecture & Session Synchronization

```
+-------------------------------------------------------+
|                 Local Agent Machine                   |
|                                                       |
|  - Playwright Chrome Automation (main_automate.js)   |
|  - IMAP OTP Listener (watch_live_otp.py)              |
+---------------------------+---------------------------+
                            |
           (1) GET credentials / (2) POST cookies
                            v
+-------------------------------------------------------+
|             AWS Production REST Server                |
|             http://13.235.142.203:5000                |
|                                                       |
|  - /ikea_login (GET company creds & session status)   |
|  - /ikea_login (POST updated session cookies)         |
|  - /login (JWT Token Authentication for APIs)         |
+-------------------------------------------------------+
```

### Architecture Principles:
- **Centralized Session Authority**: Active session cookies and credentials are stored and validated on the production REST server (refer to [AGENTS.md](file:///home/venkatesh/code/erp/backend/.agents/AGENTS.md) for the Production REST Base URL).
- **Dynamic Credential Fetching**: Authentication credentials are fetched dynamically at runtime. No user passwords or credentials are stored inside skill documentation.
- **Session Persistence**: Automated scripts fetch credentials, execute site login, and post back updated cookies (`context.cookies()`) to production.

---

## 2. IKEA (LeverEDGE) Authentication Pipeline

### Primary Deterministic Script: `main_automate.js`
Location: `/home/venkatesh/code/erp/playwright/main_automate.js`

### Execution Commands:
```bash
cd /home/venkatesh/code/erp/playwright

# Requires target company_name parameter:
node main_automate.js <company_name>
```

> [!IMPORTANT]
> **Parameter Note**: `<company_name>` must be the target operational company entity name, **NOT** the high-level user account name. Executions operate strictly per company. Refer to [AGENTS.md](file:///home/venkatesh/code/erp/backend/.agents/AGENTS.md) for User vs. Company mappings.

### Execution Protocol:
1. **Status Verification**: Query `GET /ikea_login?company=<company_name>&key=ikea`. If `is_logged_in: true`, skip login.
2. **Browser Launch**: Launch Playwright Chromium with stealth plugin and remote debugging (`port: 9222`).
3. **Credential Input**: Enter `userName`, `password`, and `databaseName` using keypress delays (`pressSequentially`).
4. **OTP Selection**: Select Email OTP (`#btn001`), confirm modal selection (`.messager-button a`).
5. **Live IMAP OTP Extraction**: Execute `watch_live_otp.py <triggerTimestamp> <company_name>` to poll the mapped email inbox for newly arrived OTP emails received after the trigger timestamp.
6. **OTP Submission**: Enter code into `#otp_input` or `#email_otp_input` via `pressSequentially()`, submit (`#otp_btn` / `#email_otp_btn`), and verify navigation.
7. **Cookie Post**: Post updated `context.cookies()` back to `POST /ikea_login`.

---

## 3. GST & eInvoice Portal Authentication Protocol

The GST and eInvoice portal logins follow a structured 3-step sequence via the backend REST API:

### Step 1: User JWT Token Authentication
Submit backend user credentials to obtain an API access token (refer to [AGENTS.md](file:///home/venkatesh/code/erp/backend/.agents/AGENTS.md) for Production Base URL, User accounts, and passwords):
- **Endpoint**: `POST /login`
- **Payload**: `{"username": "<username>", "password": "<password>"}`
- **Response**: `{"access": "<access_token>", "refresh": "<refresh_token>"}`
- **Header Requirement**: Attach `Authorization: Bearer <access_token>` to all subsequent requests.

### Step 2: Portal Session Status Verification
Before executing GST or eInvoice operations (such as GSTR reconciliation or invoice generation):
- **Verification**: The API checks portal session validity (`client.is_logged_in()`).
- **Logged-Out Signal**: If the portal session is inactive/expired, the backend returns **HTTP 501** with `{"key": "gst"}` or `{"key": "einvoice"}`.

### Step 3: Captcha Retrieval & Autonomous Agent Vision Login (On HTTP 501)
When HTTP 501 is returned, initiate the backend login flow:
1. **Fetch & Save Captcha PNG**:
   - **Endpoint**: `POST /custom/captcha`
   - **Payload**: `{"key": "gst"}` or `{"key": "einvoice"}`
   - **Returns**: PNG image buffer (`image/png`). Save bytes to `captcha.png`.
2. **Autonomous Agent Vision Captcha Resolution**:
   - **Do NOT ask the user for Captcha text**.
   - The AI Agent opens `captcha.png` using the `view_file` tool to visually read and transcribe the Captcha alphanumeric text.
3. **Submit Transcribed Captcha**:
   - **Endpoint**: `POST /custom/login`
   - **Payload**: `{"key": "gst"|"einvoice", "captcha": "<transcribed_captcha_text>"}`
   - **Response**: `{"ok": true}` confirms session cookies/tokens are active on the production backend. If `invalid_captcha`, re-fetch Captcha PNG and repeat vision read.

---

## 4. Deterministic Debug-First Workflow (When Automations Fail)

> [!CAUTION]
> **Debugging Protocol**: If an automated login fails or stalls (e.g. site layout changes, new modal popups appear, rate limits hit), **NEVER** make blind guesses or assume reasons without inspecting empirical DOM evidence.

### Step 1: DOM & Page State Inspection
1. Capture DOM HTML and Screenshot:
   ```javascript
   const html = await page.content();
   fs.writeFileSync('debug_dom.html', html);
   await page.screenshot({ path: 'debug_screen.png' });
   ```
2. Extract Page Text & Detect Email Masks:
   - Query body text to check for prompt messages (e.g. `OTP has been sent to your Email Id d********3@gmail.com`).
   - Match the masked pattern (`d********3@gmail.com`) to determine which registered inbox receives the OTP BEFORE running IMAP checks.

### Step 2: Modal & Button Selector Identification
- Inspect dialog containers (e.g. jQuery EasyUI modal `.messager-button a`, `#btn001`, `.l-btn`).
- Verify input elements (`#otp_input`, `#email_otp_input`) and ensure keypress events fire (`pressSequentially`).

### Step 3: Production Django Stacktrace Debugging
When production API calls fail (e.g. HTTP 500 error or Django HTML debug response):
1. Intercept and extract the full error response body and stacktrace snippet.
2. Synthesize the root cause from empirical log evidence.
3. Present the failure report to the user and **WAIT for user confirmation** before making code changes.
