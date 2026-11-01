# Camply

Every campaign. One platform. Camply lets advertising agencies manage Meta Ads, Google Ads, TikTok Ads and
ChatGPT Ads for many clients from one dashboard. First customer: PRception Media, Thiruvananthapuram.

**Stack:** Python 3.13 · Django 5.2 (LTS) · MongoDB 8 via the official `django-mongodb-backend` · plain HTML, CSS
and JavaScript (Django templates, no build step) · django-allauth (email + password, Google, Microsoft, two-step
verification) · Celery + Redis for background sync · Chart.js for charts.

Reference material is in [`docs/`](docs): the product blueprint, the colour guide and the dashboard mockup.

## Project layout

```
Camply/
├── backend/            Django project (Python): runs on the server
│   ├── manage.py
│   ├── camply/         settings, URLs, WSGI, Celery
│   ├── accounts/  workspace/  ads/  billing/  audit/  dashboard/
│   ├── leads/  creatives/  automation/  console/
│   ├── mongo_migrations/   tests/
│   ├── requirements.txt    pytest.ini    gunicorn.conf.py
├── frontend/           What the browser receives
│   ├── templates/      HTML pages (Django templates)
│   └── static/         CSS, JavaScript, images, vendored Lucide and Chart.js
├── docs/               Blueprint, colour guide, mockup
├── .env                Local settings (not committed; see .env.example)
└── start.bat / start.ps1   One-click local start
```

The backend reads templates and static files from `frontend/` (see `FRONTEND_DIR` in
`backend/camply/settings.py`). Run Django commands from the repository root as `python backend/manage.py …`,
or from inside `backend/`.

## Run it locally (Windows)

```powershell
python -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt
copy .env.example .env        # then fill in DJANGO_SECRET_KEY, FIELD_ENCRYPTION_KEY, CAMPLY_DEMO_PASSWORD
```

**Quick start (after the first-time setup below):** double-click `start.bat`. It starts MongoDB if it isn't
running, applies any new migrations, starts the app and opens http://127.0.0.1:8000. Close the window or press
Ctrl+C to stop the app. Don't use VS Code's "Go Live" (port 5500): it only lists files and can't run Django.

Start MongoDB, either with Docker (`docker compose up -d`) or with the portable server in `.mongodb/`:

```powershell
.\.mongodb\mongodb-win32-x86_64-windows-8.0.34\bin\mongod.exe --dbpath .mongodb\data --bind_ip 127.0.0.1
```

Then, in another terminal:

```powershell
.venv\Scripts\python backend\manage.py migrate
.venv\Scripts\python backend\manage.py seed_demo      # PRception Media demo workspace
.venv\Scripts\python backend\manage.py runserver
```

Open http://127.0.0.1:8000 and sign in as `farsana@prception.test` (Owner) with the `CAMPLY_DEMO_PASSWORD`
from `.env`. Other demo users: `arjun@` (Campaign manager), `diya@` (Analyst), `accounts@` (Finance), all
`@prception.test`, and `marketing@kovalambay.test` (Client).

Run the tests (MongoDB must be running): `cd backend` then `..\.venv\Scripts\python -m pytest`

## Deploying (Render)

The live site uses its own database, so accounts made on your PC don't exist there. To create your admin
account on the live site, add these environment variables in Render, then redeploy:

- `CAMPLY_ADMIN_EMAIL` and `CAMPLY_ADMIN_PASSWORD`: your login
- `CAMPLY_ORG_NAME`: optional; also makes you Owner of that agency. Leave it out for a pure platform admin

Use these commands (the admin account is set up automatically when the web server starts). In Render, set
**Root Directory** to `backend`, or keep the root and use the `cd backend &&` forms:

```
Build:  pip install -r requirements.txt
Start:  cd backend && python manage.py collectstatic --noinput && python manage.py migrate && gunicorn camply.wsgi
```

The password is only set when the account is created (set `CAMPLY_ADMIN_RESET_PASSWORD=true` to force it).
Platform admins sign in to the console at `/platform/`: every agency and user, and the data editor at `/admin/`. A redeploy also clears any
"Too many failed login attempts" block.

## How it is organised

| App | What it owns |
| --- | --- |
| `accounts` | The user model (sign in with email) |
| `workspace` | Organizations (tenants), clients, memberships, roles, invitations; **permissions matrix** and **tenant scoping** |
| `ads` | Platform connections, ad accounts, campaigns → ad sets → ads, daily metrics; the **platform adapter** layer and sync |
| `billing` | Internal client wallet ledger and GST invoices |
| `audit` | Audit log of every change |
| `dashboard` | Dashboard, campaigns, reports, CSV export |

### Rules the code enforces

- **Multi-tenant.** Every query for tenant data goes through `workspace.scoping.scope()`, which limits it to the
  user's organization and their assigned clients. Owners see all clients; other roles see assigned clients unless
  "access to all clients" is on.
- **Roles on the server.** `workspace/permissions.py` holds the matrix for Owner, Admin, Campaign manager, Analyst,
  Finance, Client and Viewer. Views use `@require_perm(...)`; templates only hide controls.
- **One adapter interface.** `ads/adapters/base.py` defines `AdPlatformAdapter`. Each platform declares its
  capabilities, and the UI only offers actions the platform supports.
- **Money in paise.** Amounts are stored as integer paise and shown with Indian grouping (₹4,87,320). GST is 18%,
  split CGST + SGST within the agency's state and IGST otherwise. Timezone Asia/Kolkata.
- **Wallet ≠ platform balance.** The wallet is Camply's internal client ledger, and the UI says so.
- **Every change is audited.** Pauses, resumes, syncs, ledger entries, invoices and team changes write an `AuditEvent`.

## Status

Working: sign in/up, two-step verification, Google/Microsoft sign-in (when keys are set), onboarding, clients, team
invites and roles, platform admin console, dashboard, campaigns list and detail, pause/resume, ad accounts with
sync, cross-channel report with CSV export, wallet ledger, GST invoices, audit log, **Leads** (inbox, pipeline,
website-form webhook, UTM builder, tracking health), **Creative Studio** (library, versions, platform checks,
approval workflow, S3-compatible storage), **Automation** (rules, alerts, approvals, scheduled summaries), the
scroll-story home page, light and dark mode, mobile layout.

Not built yet:
- **Live platform connections.** The Meta adapter has read and pause/resume code but has not been run against the
  real API. Google, TikTok and ChatGPT Ads adapters are stubs. Without a live connection, accounts use the
  sandbox adapter (deterministic demo data) in development.
- Campaign creation and bulk actions, report sharing and manual entry, AI Copilot, Razorpay recharge.
