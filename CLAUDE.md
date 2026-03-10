# CLAUDE.md — Case Central

This file provides guidance for AI assistants working in this repository.

## Project Overview

**Case Central** is a Frappe-based legal practice management application built by 4C Solutions. It extends ERPNext with domain-specific DocTypes for managing cases, matters, legal services, appointments, document templates, and billing for law firms.

- **App name:** `casecentral`
- **Version:** 0.0.1
- **License:** MIT
- **Author:** 4C Solutions (info@4csolutions.in)

---

## Technology Stack

| Layer | Technology |
|---|---|
| Backend language | Python 3.10 |
| Framework | [Frappe](https://github.com/frappe/frappe) (installed via `bench init`) |
| ERP integration | ERPNext |
| Database | MariaDB 10.6 (UTF8MB4) |
| ORM | Frappe's document-oriented ORM |
| Frontend | Frappe Desk UI, JavaScript/jQuery |
| Node.js | 14 |
| Package manager (JS) | Yarn |
| Document templating | `docxtpl` (Word document generation) |

---

## Repository Structure

```
casecentral/                    # Python package root
├── case_central/               # Primary module
│   ├── doctype/                # 31 custom DocTypes
│   ├── report/                 # 2 reports (matter_analytics, case_central_metrics)
│   ├── dashboard_chart/        # 9 dashboard charts
│   ├── case_central_dashboard/ # Dashboard configuration
│   └── number_card/            # 3 number cards (clients, matter, task)
├── legal_documents/            # Document management module
│   └── doctype/                # 3 DocTypes (legal_notice, legal_templates, postal_order)
├── config/                     # Desktop and docs config (desktop.py, docs.py)
├── doc_events/                 # Document event handlers
│   ├── task.py
│   ├── case.py
│   ├── sales_invoice.py
│   ├── purchase_invoice.py
│   └── timesheet.py
├── patches/v14_0/              # Database migration patches
├── fixtures/                   # Exported fixtures (custom fields, property setters, client scripts)
├── public/js/                  # Custom JS for Frappe forms
│   ├── sales_invoice.js
│   └── payment_entry.js
├── templates/                  # Jinja templates
├── hooks.py                    # Frappe app hooks (entry point for all framework integrations)
├── overrides.py                # DocType class overrides (CustomSalesInvoice)
├── utils.py                    # Shared utility functions (whitelisted API methods)
└── install.py                  # Post-install hooks
```

---

## DocType Inventory

### case_central module (31 DocTypes)

**Core legal entities:**
- `Matter` — central entity; tracks status, parties, legal services, billing rates
- `Case` — individual case linked to a matter
- `Party` / `Case Party` — parties involved in a matter
- `Case History` — audit trail of case events

**Case management:**
- `Nature of Case`, `Nature of Disposal`
- `Caveat`, `Witness Examined`
- `Interim Applications`, `Exhibits`, `Court Form`

**Legal services & billing:**
- `Legal Service`, `Legal Service Entry`, `Legal Service Rate`, `Service`, `Service Type`

**Appointments & scheduling:**
- `Customer Appointment`, `Appointment Type`
- `Lawyer Schedule`, `Lawyer Schedule Time Slot`
- `Meeting Room`, `Meeting Room Schedule`

**Books management:**
- `Book`, `Book Type`, `Lend Book`

**Configuration:**
- `Case Central Settings`, `Matter Type`, `Linked Matter`
- `File Type`, `Document Outward`

### legal_documents module (3 DocTypes)

- `Legal Notice`, `Legal Templates`, `Postal Order`

---

## Development Environment Setup

Case Central requires Frappe Bench. There is no standalone `docker-compose` or `Makefile` — Bench handles all environment orchestration.

```bash
# Install bench
pip install frappe-bench

# Initialize a new bench
bench init --skip-redis-config-generation frappe-bench
cd frappe-bench

# Get the app
bench get-app casecentral /path/to/casecentral

# Install dependencies
bench setup requirements --dev

# Create a site and install the app
bench new-site --db-root-password root --admin-password admin dev.local
bench --site dev.local install-app casecentral

# Build frontend assets
bench build

# Start the development server
bench start
```

---

## Running Tests

Tests use Frappe's built-in test framework (`FrappeTestCase`). Test files live alongside their DocType in `test_<doctype>.py` files.

```bash
# Enable tests on the site
bench --site test_site set-config allow_tests true

# Run all app tests
bench --site test_site run-tests --app casecentral

# Run tests for a specific doctype
bench --site test_site run-tests --doctype "Matter"
```

Tests are currently mostly placeholder stubs. When adding a new DocType, create the corresponding `test_<doctype>.py` using `FrappeTestCase` as the base class.

---

## CI/CD

**File:** `.github/workflows/ci.yml`

Triggered on:
- Push to `develop` branch
- All pull requests

Pipeline steps:
1. Spins up MariaDB 10.6 as a service container
2. Sets up Python 3.10 and Node 14
3. Caches pip and yarn dependencies
4. Initializes Frappe Bench
5. Configures MariaDB character set to `utf8mb4`
6. Installs app, builds assets, creates test site
7. Runs `bench run-tests --app casecentral`

Concurrency: In-progress runs are cancelled when new commits are pushed to the same PR.

---

## Key Conventions

### Frappe DocType conventions

- **Python controller:** `<doctype_name>.py` alongside `<doctype_name>.json`
- **Test file:** `test_<doctype_name>.py` in the same directory
- **Use `frappe.db.sql()`** for complex queries; prefer `frappe.get_doc()` / `frappe.get_list()` for simple CRUD
- **Whitelisted API methods** (callable from frontend) must be decorated with `@frappe.whitelist()`
- **Validate** business logic in the `validate()` method; avoid it in `before_save()` unless necessary
- Keep heavy computation out of `on_update` — prefer scheduled tasks for batch operations

### Document event handlers

Event handlers live in `casecentral/doc_events/` rather than inline in DocType controllers. This keeps controllers lean. Hooks are registered in `hooks.py`:

```python
doc_events = {
    "Task": {
        "after_insert": "casecentral.doc_events.task.after_insert",
        "on_update": "casecentral.doc_events.task.update_task_matter",
        "after_delete": "casecentral.doc_events.task.update_task_matter"
    },
    ...
}
```

### Matter status management

Matter status (`Open`, `Working`, `Pending`, `Completed`, `Cancelled`) is computed automatically based on the status of linked Tasks and Cases. Do not set matter status directly — trigger recalculation via `update_matter_status()`.

### Fixtures

Custom Fields, Property Setters, and Client Scripts are managed as Frappe fixtures (exported to JSON and committed). To update fixtures after making changes in the UI:

```bash
bench --site dev.local export-fixtures
```

Never hand-edit fixture JSON files unless correcting a specific field value.

### DocType class overrides

`Sales Invoice` is overridden with `CustomSalesInvoice` in `overrides.py`. This allows legal service import functionality. When extending standard ERPNext DocTypes, always use overrides rather than patching core files.

```python
# hooks.py
override_doctype_class = {
    'Sales Invoice': 'casecentral.overrides.CustomSalesInvoice'
}
```

### Frontend JavaScript

Custom JS for standard DocTypes is loaded via `hooks.py`:

```python
doctype_js = {
    "Sales Invoice": "public/js/sales_invoice.js",
    "Payment Entry": "public/js/payment_entry.js"
}
```

The main app bundle (`casecentral.bundle.js`) is included in the Desk header for app-wide JS.

---

## Scheduled Tasks

Two daily scheduled tasks run automatically:

| Task | Purpose |
|---|---|
| `caveat.set_expired_status` | Marks caveats as expired when their deadline passes |
| `customer_appointment.update_appointment_status` | Syncs appointment statuses based on timesheets |

Registered in `hooks.py` under `scheduler_events["daily"]`.

---

## Installation Hook

`install.py` runs after `bench install-app`. It currently creates a "Books" item group in ERPNext. Any one-time setup logic for new installations belongs here.

---

## Reporting

Two custom report modules under `case_central/report/`:

- **`matter_analytics`** — Multi-filter report with pie charts for matter distribution analysis
- **`case_central_metrics`** — Line chart report for case clearance rate analysis

Reports follow Frappe's standard script report pattern (Python + JS files in the report directory).

---

## Git Workflow

- Default development branch: `develop`
- CI runs on push to `develop` and on all PRs
- Follow conventional commit style: `feat:`, `fix:`, `chore:`, `refactor:` prefixes
- Keep commits focused and atomic

---

## Common Pitfalls

1. **Do not push to `master` directly** — all development flows through `develop` and PRs.
2. **Fixtures must be re-exported** after any UI-driven customization to keep JSON in sync.
3. **Do not invoke `update_matter_status()` in a loop** — it triggers DB writes per call.
4. **`docxtpl` dependency** — Word template generation requires this package; it is listed in `requirements.txt` and installed via `bench setup requirements`.
5. **MariaDB character set** — Must be set to `utf8mb4` before creating a site, or multi-byte characters will fail to save.
6. **Node 14 is required** — Newer Node versions may cause Frappe asset build failures.
