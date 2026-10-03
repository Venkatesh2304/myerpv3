# Master Domain Guidelines: Users vs. Companies & Organizations

This document provides top-level contextual guidance on the fundamental distinction between **Users**, **Organizations (Company Groups)**, and **Companies** across the ERP codebase and agent skills.

---

## 1. Production Server Base URL & User Accounts

- **Production REST Base URL**: `http://13.235.142.203:5000` (All API endpoints are relative to this base URL).
- **Default User Password**: All production users use password **`1`** for JWT authentication (`POST /login`).

| Production Username | Password | Mapped Operational Companies (`Company`) | Role / Scope |
| :--- | :---: | :--- | :--- |
| **`sathish`** | `1` | `devaki_hul` | Single Company Operational Manager |
| **`lakme`** | `1` | `lakme_rural`, `lakme_urban` | Sister Company Group Manager |
| **`sathish_gst`** | `1` | `devaki_hul`, `lakme_rural`, `lakme_urban` | Monthly GST & eInvoice Filing User (Consolidated Organization) |
| **`murugan_gst`** | `1` | `murugan_hul` | Monthly GST & eInvoice Filing User (`murugan_hul`) |

---

## 2. Organization (Company Group) Concept

- **`Organization` Model**: Binds sister operational companies together under a shared organizational entity in Django (`core.Organization`).
- **GST & eInvoice Grouping**: Sister companies under the same `Organization` (e.g. `devaki_hul`, `lakme_rural`, `lakme_urban`) share a consolidated GSTIN registration. 
- **Filing User Scope**: High-level filing accounts like `sathish_gst` authenticate at the `Organization` level to query and reconcile aggregated GSTR-1, GSTR-2B, and eInvoice data across all sister companies in the group.
- **Single Company Scope**: Individual operational actions (IKEA LeverEDGE session cookie update, inventory ingestion, Tally stock simulations) run strictly per operational `<company_name>`.

---

## 3. Core Operational Rules across All Skills

1. **User JWT Authentication**: Always pass `{"username": "<username>", "password": "1"}` to `POST /login` to obtain `Bearer <access_token>`.
2. **Strict Parameter Distinction**:
   - `<username>` (e.g., `sathish_gst`) is used for REST API JWT authentication (`POST /login`).
   - `<company_name>` (e.g., `lakme_urban`) is the mandatory parameter passed to single-company execution scripts (such as `node main_automate.js <company_name>` or `python3 manage.py monthly_gst <company_name>`).

---

## 4. Production Server SSH Access & Strict Usage Clause

- **SSH Command**: `ssh -4 -i /home/venkatesh/Downloads/billingv2.pem ubuntu@13.235.142.203`
- **Bash Alias**: `ssh-server`
- **Remote Backend Path**: `/home/ubuntu/myerpv3`

> [!CAUTION]
> **Strict SSH Access Clause**:
> 1. **Read-Only / Debug-Only**: SSH access is strictly reserved for read-only inspection, log viewing, and troubleshooting.
> 2. **Not a First Resort**: Agents MUST NOT SSH into the server as a first resort. All normal operations must be performed via the REST API endpoints or local Playwright/automation playbooks.
> 3. **Explicit Trigger Only**: Use `ssh-server` or remote SSH execution ONLY when explicitly requested by the user or mandated by a specific skill SOP during severe troubleshooting steps.


