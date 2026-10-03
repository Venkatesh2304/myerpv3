# App: `core` — Foundation, Multi-Tenancy & External Auth Bridge

> Purpose: Core multi-tenancy, user authentication, external portal session persistence, and IKEA token sync bridge.

---

## 1. Business Purpose & Role

The `core` app provides the base data models and authentication infrastructure for the entire ERP system. It serves two distinct purposes:
1. **Internal Multi-Tenancy**: Scopes all ERP entities (bills, ledger, stocks, reports) to a tenant [`Organization`](file:///home/ubuntu/myerpv3/core/models.py#L16) and an operational [`Company`](file:///home/ubuntu/myerpv3/core/models.py#L19) (e.g. `devaki_urban` vs `devaki_rural`).
2. **External Portal Session Store**: Holds external credentials and active session cookies for third-party portals (IKEA Leveredge, GST, E-Invoice, Unilever SAP) in [`UserSession`](file:///home/ubuntu/myerpv3/core/models.py#L27).
3. **IKEA Token Sync Bridge**: Exposes endpoints for local distributor desktop clients to push fresh IKEA cookies and for automated AWS ECS Fargate tasks to regenerate tokens.

---

## 2. Core Models

### [`Organization`](file:///home/ubuntu/myerpv3/core/models.py#L16)
- **Primary Key**: `name` (CharField).
- Top-level distributor entity.

### [`Company`](file:///home/ubuntu/myerpv3/core/models.py#L19)
- **Primary Key**: `name` (CharField).
- **Foreign Key**: `organization` $\rightarrow$ `Organization`.
- **Fields**:
  - `gst_types` (JSONField): List of invoice types applicable for GST filing (e.g., `["sales", "damage"]`).
  - `print_types` (JSONField): Supported print modes (e.g., `["first_copy", "loading_sheet"]`).
  - `einvoice_enabled` (BooleanField): Whether B2B E-Invoicing applies to this division.
  - `emails` (JSONField): Email recipient list for automated reports and alerts.

### [`User`](file:///home/ubuntu/myerpv3/core/models.py#L9)
- Extends `AbstractUser` with primary key `username`.
- Tied to a single `organization` and Many-to-Many `companies`.
- JSONField `permissions`.

### [`UserSession`](file:///home/ubuntu/myerpv3/core/models.py#L27)
- **Composite Primary Key**: `(user, key)` where `user` is the company or organization name, and `key` is the service (`"ikea"`, `"ikea_bank"`, `"gst"`, `"einvoice"`, `"unilever"`).
- **Fields**:
  - `username`, `password`: External portal login credentials.
  - `cookies` (JSONField): Array of serialized cookie dictionaries (`name`, `value`, `domain`, `path`).
  - `config` (JSONField): Service configuration (e.g., `dbName`, portal base URL `home`, `auto_delivery_process`).
- **Method**: `update_cookies(cookies: RequestsCookieJar)` serializes requests cookies and updates the database record.

### [`CompanyModel`](file:///home/ubuntu/myerpv3/core/models.py#L52)
- Abstract base model inherited across `bill`, `erp`, `report`, `bank`, and `product_scan`.
- Provides `company = ForeignKey("core.Company", on_delete=models.CASCADE, db_index=True)`.

---

## 3. Key Endpoints & APIs

| Endpoint | Method | Permission | Purpose / Parameters |
| :--- | :--- | :--- | :--- |
| `/login` | `POST` | AllowAny | JWT login endpoint via `TokenObtainPairView`. Returns access & refresh tokens. |
| `/companies` | `GET` | Authenticated | Returns the list of `Company` entities associated with the current user. |
| `/usersession` | `GET`, `POST` | Authenticated | `GET`: Fetch active external session usernames. `POST`: Update external credentials. |
| `/ikea_login` | `GET`, `POST` | AllowAny | **Local Desktop Client Bridge**: `GET` returns credentials & DB name. `POST` receives `{company, key, cookies}` from the local desktop client to update `UserSession`. |
| `/trigger_ikea_login` | `GET` | AllowAny | Checks all users. If any IKEA session is dead, invokes AWS ECS Fargate task (`ikeatoken`) in `ap-south-1` to solve enterprise captcha and email results. |
| `/ikea_health` | `GET` | AllowAny | Probes IKEA session health across all companies and sends an email status report. |

---

## 4. How External Session Sync Works

```
[Distributor Local Desktop PC]
      |
      | 1. Logs into IKEA with Recaptcha / MFA
      | 2. Captures session cookies
      v
POST /ikea_login  { company, key, cookies }
      |
      v
[core.views.ikea_login]
      |
      | 3. Writes cookies to UserSession table
      v
[custom.classes.Session / BaseIkea]
      |
      | 4. Next API call automatically loads fresh cookies from DB
      v
IKEA API Requests Succeed!
```

If the desktop client is offline, `/trigger_ikea_login` can spin up an AWS ECS Fargate task with container `IkeaToken` to solve Recaptcha in the cloud.

---

## 5. Edge Cases & Gotchas

1. **Unauthenticated `/ikea_login`**: `/ikea_login` has `permission_classes=[AllowAny]` because external desktop clients and background sync tools push tokens without holding JWT distributor user sessions.
2. **Composite Primary Keys**: `UserSession` uses `CompositePrimaryKey("user", "key")`. Always query via `UserSession.objects.get(user=company, key=key)`.
3. **Cookie Expiration**: IKEA sessions expire after idle time. If `is_logged_in()` fails, downstream apps receive status `501`, prompting the desktop client or user to re-authenticate.
