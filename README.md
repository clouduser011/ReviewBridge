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
- Monitoring dashboard with charts, review list, ticket feed, and logs
- **Instant app search**: local catalog (2500+ apps) with exact app-name match ranking; Play Store fallback when needed

## Tech Stack

- Backend: Flask + SQLAlchemy + Jinja2
- Database: SQLite (local, zero setup)
- NLP: TextBlob
- Integrations: `google-play-scraper`, Jira REST API, Zendesk API
- Frontend: Bootstrap 5 + Chart.js

## Project Structure

- `run.py` - app entrypoint
- `app/routes.py` - home, analysis workspace, CSV upload, Google Play fetch endpoints
- `app/google_play.py` - live Google Play review fetching
- `app/app_catalog.py` - local app catalog search and name-first ranking
- `data/app_catalog.json` - built app catalog (generate via script below)
- `app/ticketing.py` - Jira/Zendesk real + fallback ticket creation
- `app/templates/home.html` - marketing landing page
- `app/templates/analysis.html` - analysis workspace UI
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

Go to **Analysis** (`/analysis`) to fetch reviews and view results.

## Configure Real Ticket APIs

Edit `.env`:

- Jira:
  - `JIRA_BASE_URL=https://your-domain.atlassian.net`
  - `JIRA_EMAIL=you@example.com`
  - `JIRA_API_TOKEN=...`
  - `JIRA_PROJECT_KEY=RA`
- Zendesk:
  - `ZENDESK_SUBDOMAIN=your-subdomain`
  - `ZENDESK_EMAIL=you@example.com`
  - `ZENDESK_API_TOKEN=...`

If credentials are missing, the app automatically uses mock ticket IDs so demo still works.

## How To Use

1. Open the home page, then click **Start analysis** (or go to `/analysis`)
2. Use **Live Google Play** to import real reviews by package name
3. Or use **Upload CSV** for offline/demo mode
4. Review analysis results, generated tickets, and processing logs on the analysis page

## App search catalog (recommended once)

Build the local catalog used for instant, exact-first app suggestions on the Analysis page:

```powershell
python scripts/build_app_catalog.py
```

This writes `data/app_catalog.json` (target: 2500+ unique apps). Requires network access to Google Play search.

Check status: `GET /api/app-catalog/status`

## Notes

- **Storage diagnostics**: `GET /api/storage-health` returns JSON comparing review and ticket counts (useful if tickets seem higher than reviews).
- The analysis workspace (`/analysis`) is intentionally **clean** on each visit or refresh. After a fetch or upload you are redirected to `/analysis?since=<iso-timestamp>` to view that batch; use **History** for all stored data.
- `/dashboard` redirects to `/analysis` for backward compatibility.
- The app is production-style for FYP submission and demo-ready.
- You can further improve by adding authentication, role-based access, and background job queue.
