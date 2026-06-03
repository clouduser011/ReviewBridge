# ReviewBridge - Final Year Project

AI-powered web application that fetches Google Play reviews, performs sentiment + intent analysis, classifies issue types, and creates Jira/Zendesk tickets automatically.

## Features

- Live Google Play review import by package name (`com.company.app`)
- CSV upload fallback (`author,rating,content`)
- NLP sentiment analysis using TextBlob
- Category detection: bug, feature request, support, complaint
- Duplicate prevention using review hashing
- Automatic ticket routing:
  - Jira for bug/feature tasks
  - Zendesk for support/complaint tasks
- Real API mode for Jira and Zendesk (credentials via `.env`)
- Analysis workspace with charts, review list, ticket feed, and logs
- **Instant app search**: local catalog (6200+ apps, Pakistan-focused) with exact app-name match ranking; Play Store fallback when needed
- **User accounts**: sign up / sign in, per-user History, account settings, and optional Jira/Zendesk integrations

## Access model

| Feature | Anonymous | Logged-in user |
|---------|-------------|----------------|
| Analysis (fetch, CSV, charts, sentiment) | Yes | Yes |
| History + export/clear | No (login required) | Yes — own data only |
| Batch export on Analysis | Yes (current session batch) | Yes |
| Integration settings | No | Yes (`/account/settings`) |
| Ticketing (Jira/Zendesk) | No | Yes — real API if configured, else demo/mock |

Auth URLs: `/auth/login`, `/auth/signup`, `/account/settings`

## Authentication

- **Signup:** min 8 characters, instant login after account creation
- **Sign in:** email/password
- **Profile:** display name, optional password change
- **Delete account:** password + email confirmation

## Tech Stack

- Backend: Flask + SQLAlchemy + Jinja2 + Flask-Login
- Database: SQLite (local, zero setup)
- NLP: TextBlob
- Integrations: `google-play-scraper`, Jira REST API, Zendesk API
- Frontend: Bootstrap 5 + Chart.js

## Project Structure

- `run.py` - app entrypoint
- `app/routes.py` - home, analysis workspace, history, CSV upload, Google Play fetch endpoints
- `app/auth.py` - login, signup, logout
- `app/account.py` - profile, integrations, account deletion
- `app/user_context.py` - owner scoping for batches and tickets
- `app/crypto_utils.py` - encrypted storage for integration API tokens
- `app/google_play.py` - live Google Play review fetching
- `app/app_catalog.py` - local app catalog search and name-first ranking
- `app/storage_health.py` - review vs ticket storage diagnostics
- `app/ticketing.py` - Jira/Zendesk real + fallback ticket creation
- `app/templates/home.html` - marketing landing page
- `app/templates/analysis.html` - analysis workspace UI
- `app/templates/history.html` - archived reviews, tickets, and logs
- `app/static/js/analysis.js` - analysis workspace (pipeline, charts, app search)
- `app/static/js/history.js` - history page interactions
- `app/static/js/review-filter.js` - shared review table filter toolbar
- `scripts/build_app_catalog.py` - build `data/app_catalog.json` (6200+ PK-focused apps)
- `scripts/test_pipeline.py` - smoke tests for routes, templates, and pipeline helpers
- `data/app_catalog.json` - built app catalog (generate via script below)
- `data/pk_priority_apps.json` - curated PK apps for catalog bootstrap
- `data/app_catalog.build_state.json` - catalog build resume state (created by builder)
- `data/sample_reviews.csv` - demo upload file

## Quick Start (Windows)

```powershell
cd "c:\Users\Rehman\Desktop\ReviewBridge"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python run.py
```

Open: http://127.0.0.1:5000 (home page)

Go to **Analysis** (`/analysis`) to fetch reviews and view results. Create an account at `/auth/signup` to save History and enable ticketing.

## Configure Real Ticket APIs

**Per-user (recommended):** sign in → **Account settings** → **Integrations**. Enable Jira and/or Zendesk, enter credentials, and use **Test connection**. Tokens are encrypted at rest.

**Global fallback (optional dev):** edit `.env`:

- Jira:
  - `JIRA_BASE_URL=https://your-domain.atlassian.net`
  - `JIRA_EMAIL=you@example.com`
  - `JIRA_API_TOKEN=...`
  - `JIRA_PROJECT_KEY=RA`
- Zendesk:
  - `ZENDESK_SUBDOMAIN=your-subdomain`
  - `ZENDESK_EMAIL=you@example.com`
  - `ZENDESK_API_TOKEN=...`

If credentials are missing, logged-in users still get **mock ticket IDs** so demos work without external APIs.

## How To Use

1. Open the home page, then click **Start analysis** (or go to `/analysis`)
2. Optional: **Sign up** at `/auth/signup` for History and ticketing
3. Use **Live Google Play** to import real reviews by package name
4. Or use **Upload CSV** for offline/demo mode
5. Review analysis results; signed-in users also see generated tickets and processing logs
6. Open **History** (login required) for all saved reviews, tickets, and logs

## App search catalog (recommended once)

Build the local catalog used for instant, exact-first app suggestions on the Analysis page. The builder is **Pakistan-focused**: it merges your existing catalog, bootstraps must-have PK apps from [`data/pk_priority_apps.json`](data/pk_priority_apps.json), then searches Google Play on **pk → in → us** storefronts.

```powershell
python scripts/build_app_catalog.py --resume --target 6200
```

Monitor progress:

```powershell
python scripts/build_app_catalog.py --status
```

This writes `data/app_catalog.json` (target: **6200+** unique apps). Requires network access to Google Play. If interrupted, re-run the same `--resume` command. Expected duration: about **30–90 minutes** for a full PK-focused expansion.

Check status: `GET /api/app-catalog/status`

## Testing

```powershell
python scripts/test_pipeline.py
```

## Notes

- **Database**: default SQLite file is `instance/reviewbridge.db`. If an older `instance/review_analyzer.db` exists and the new file does not, the app uses the legacy file automatically. Override with `DATABASE_URL` in `.env`.
- **Storage diagnostics**: `GET /api/storage-health` returns JSON comparing review and ticket counts (useful if tickets seem higher than reviews).
- The analysis workspace (`/analysis`) is intentionally **clean** on each visit or refresh. After a fetch or upload you are redirected to `/analysis?since=<iso-timestamp>` to view that batch; use **History** (when signed in) for all stored data.
- Legacy URLs redirect for backward compatibility: `/dashboard` → `/analysis`; `/export/dashboard.csv` and `/export/dashboard.xlsx` delegate to the analysis export endpoints; `POST /dashboard/clear` clears the current analysis batch.
- The app is production-style for FYP submission and demo-ready.
