# AI Agent Knowledge Base & Architecture Index

This codebase serves as the backend ERP, automation, and reconciliation engine for an **Enterprise HUL Distributor** running on an **AWS Ubuntu EC2 instance with limited RAM**.

Before implementing features or debugging, consult these concise domain guides:

1. **[System Architecture & Constraints](file:///home/ubuntu/myerpv3/docs/SYSTEM_OVERVIEW.md)**
   - Hardware limits (EC2, limited RAM, Gunicorn concurrency, CPU quotas).
   - Port mappings (Backend: `http://13.235.142.203:5000`, Frontend: `8000`).
   - Domain context (HUL distribution, IKEA Leveredge, GST, NIC E-Invoice, Unilever SAP).
   - Multi-tenancy structure (`Organization` $\rightarrow$ `Company` $\rightarrow$ `User` / `UserSession`).

2. **[Django Apps & Workflows Matrix](file:///home/ubuntu/myerpv3/docs/APPS_GUIDE.md)**
   - App-by-app guide for all 12 apps (`core`, `erp`, `gst`, `bill`, `load`, `product_scan`, `report`, `printing`, `bank`, `misc`, `bill_scan`, `ledger`).
   - Deep dives into core workflows:
     - Purchase Product Load Check (`load` app).
     - Bank Statement Reconciliation & ML Matching (`bank` app).
     - Market Order Billing & Delivery Dispatch (`bill` + `bill_scan`).
     - Sales Box Packing Audit (`product_scan` app).
     - Monthly GST Return & E-Invoice Lifecycle (`gst` + `erp`).
   - "Where Do I Solve X?" quick-reference table.

3. **[Custom Scraper Classes & Integration Rules](file:///home/ubuntu/myerpv3/docs/CLASSES_GUIDE.md)**
   - Pure `requests`-based cURL architecture (`custom/curl/` $\rightarrow$ `all_curls.py` $\rightarrow$ `get_curl` $\rightarrow$ `curl_replace`).
   - Authentication protocols:
     - **IKEA**: Local Windows client pushes session; server cannot log in directly.
     - **GST / E-Invoice**: Captcha solving; **strict $\ge 5$ attempts failure ban risk**.
   - Session state management with the `@ikea_screen` decorator.
   - **Semantic Report Disambiguation Resolver**: Map business queries to exact IKEA methods (avoiding blind greps for "outstanding", "stock", etc.).
   - Procedure for fixing scrapers when upstream portal APIs change.
