# Daily Global Tech News Scheduler

A beginner-friendly Python project that collects technology news once a day, categorizes and scores the articles, stores them in MongoDB, creates a daily briefing, and provides read-only REST API endpoints to browse the stored information.

## Features

- Fetches recent technology articles from NewsAPI.org.
- Validates article titles and URLs, assigns a category, and calculates a simple importance score.
- Stores articles and daily briefings in MongoDB.
- Prevents duplicate article URLs and duplicate briefing dates with MongoDB unique indexes.
- Runs the workflow on a configurable daily schedule.
- Provides REST endpoints and interactive Swagger documentation.
- Includes automated tests that use mocks for NewsAPI and MongoDB operations.

## Technology and Simple Architecture

- **Python** runs the application code.
- **Requests** calls the NewsAPI.org endpoint.
- **PyMongo** connects to MongoDB Community Server.
- **python-dotenv** reads local settings from `.env`.
- **APScheduler** triggers the daily workflow.
- **FastAPI** provides the read-only REST API and application lifespan.
- **Uvicorn** serves the FastAPI application.
- **Postman** can be used to send and inspect API requests.

The main modules work together as follows:

1. `config.py` loads settings from `.env`.
2. `news_service.py` fetches and normalizes article data from NewsAPI.org.
3. `news_storage.py` validates articles, categorizes and scores them, and inserts them into MongoDB.
4. `briefing_service.py` selects stored articles and creates a briefing for the schedule's current date.
5. `scheduler.py` registers the configured daily job and calls the fetch, storage, and briefing workflow.
6. `api.py` exposes read-only endpoints and starts/stops an APScheduler instance using FastAPI's lifespan.
7. `database.py` reuses the MongoDB client, checks connectivity, and prepares collections and indexes.

The normal workflow is **fetch news → validate articles → categorize and score → store articles → generate and store the daily briefing**. If fetching or saving fails, later workflow steps are not run. Briefing suggestions are labeled as generated suggestions rather than reported facts or real job listings.

## Prerequisites

- Windows with PowerShell (commands below use PowerShell syntax).
- Python installed and available as `python`.
- MongoDB Community Server installed and running locally, or access to a MongoDB server whose URI you are allowed to use.
- A NewsAPI.org API key for live scheduled fetching.
- Internet access for dependency installation and the NewsAPI request.

## Fresh Clone Setup

Open PowerShell in the cloned project folder. Create and activate a virtual environment, then install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Copy the safe template to a local environment file:

```powershell
Copy-Item .env.example .env
```

Edit `.env` using a text editor. Set the NewsAPI key and confirm the MongoDB URI and schedule settings. Do not commit `.env`, paste its contents into issues or chat, or print the key in logs. `.env` and `.venv/` are excluded by `.gitignore`; `.env.example` is the safe, tracked template.

## MongoDB Setup

Start MongoDB Community Server and make sure it is listening at the URI in `.env` (the default is `mongodb://localhost:27017/`). You do not need to create the database or collections manually. At API startup, the application pings MongoDB and prepares the existing `news` and `daily_briefings` collections, including unique indexes on `news.url` and `daily_briefings.briefing_date`.

The API will not finish starting if MongoDB cannot be reached or the required indexes cannot be prepared. Check the MongoDB service, URI, and database permissions if startup fails.

Optional database check (this connects to the configured database and creates/verifies its indexes; it does not insert news or briefing documents):

```powershell
.\.venv\Scripts\python.exe .\test_database.py
```

## NewsAPI Configuration

Create or access your NewsAPI.org account and copy its API key to the `NEWS_API_KEY` setting in `.env`. The configured base URL should be `https://newsapi.org/v2`. Keep the key private. The application sends it to the provider in the `X-Api-Key` request header and does not include it in application logs.

## Environment Variables

| Variable | Purpose | Example/default |
| --- | --- | --- |
| `MONGODB_URI` | MongoDB connection string | `mongodb://localhost:27017/` |
| `DATABASE_NAME` | Database used by the application | `tech_news` |
| `NEWS_API_KEY` | Private NewsAPI.org key | Set in `.env`; blank by default |
| `NEWS_API_BASE_URL` | NewsAPI.org API base URL | `https://newsapi.org/v2` in `.env.example`; code default is blank |
| `NEWS_SCHEDULE_HOUR` | Daily schedule hour, 0–23 | `6` |
| `NEWS_SCHEDULE_MINUTE` | Daily schedule minute, 0–59 | `0` |
| `NEWS_SCHEDULE_TIMEZONE` | IANA time-zone name for schedule and briefing date | `Asia/Kolkata` |
| `NEWS_FETCH_LIMIT` | Maximum requested articles per fetch, 1–100 | `100` |

`config.py` loads local values from `.env` and provides defaults. Ensure the schedule hour and minute are valid integers, the fetch limit is between 1 and 100, and the time zone is a valid IANA name.

## Start the API

Make sure MongoDB is running and `.env` has the needed values. From the project root, run the project’s API command:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api:app --reload
```

The `--reload` option is useful during local development; Uvicorn reloads when source files change. The FastAPI application is `app` in `api.py` (not `main.py`). Use a single worker for this in-process scheduler. Multiple worker processes each create their own scheduler and could run the daily job more than once.

Open Swagger UI in a browser:

```text
http://127.0.0.1:8000/docs
```

The TechPulse browser dashboard is served by the same FastAPI application at:

```text
http://127.0.0.1:8000/
```

The static files are in `frontend/`. Open the dashboard through this URL rather than opening `frontend/index.html` directly or using a separate development server. Serving the page from FastAPI keeps frontend requests on the same origin as the API, so this local setup does not need CORS configuration. The dashboard uses the current browser origin as its API base URL.

Stop the server with `Ctrl+C`. FastAPI's lifespan handles scheduler shutdown.

## TechPulse Dashboard

The plain HTML, CSS, and JavaScript dashboard calls the existing API routes; it does not add or simulate backend capabilities. It shows the real article total, configured topic filters, backend health state, saved briefings, news fields, and article details when the corresponding responses contain them. Category filtering calls `/news/category/{category}`, keyword search calls `/news/search?keyword=...`, and the briefing is loaded from `/briefings` and `/briefings/{date}`. Article details use `/news/{article_id}`.

The nine topic filters match the category names defined in `news_storage.py`. Search and category selection are separate API filters; choosing a category clears the keyword search. The briefing view uses the stored `news`, `summary`, `why_it_matters`, `learning_of_the_day`, and `career_opportunity` fields when present. Learning and career entries are labeled as generated suggestions, not reported facts or job listings. Publisher links open in a new tab.

If the API is unavailable, the page does not mark itself Connected and displays a retry option where data failed to load. The project does not currently provide a category-list endpoint; the dashboard's filter choices correspond to categories supported by the current backend code.

## API Endpoints

All endpoints are read-only. List responses have the shape `{"items": [...], "skip": 0, "limit": 20, "total": 0}`. MongoDB ObjectIds and Python dates/datetimes are returned as strings.

| Method and path | Purpose |
| --- | --- |
| `GET /health` | Check API availability and MongoDB connectivity |
| `GET /news?skip=0&limit=20` | List articles; `limit` is 1–100 |
| `GET /news/{article_id}` | Get one article by MongoDB ObjectId |
| `GET /news/category/{category}` | List articles with an exact category |
| `GET /news/search?keyword=python` | Search titles/descriptions with a case-insensitive literal keyword |
| `GET /briefings?skip=0&limit=20` | List stored briefings |
| `GET /briefings/YYYY-MM-DD` | Get one briefing by date |

In Postman, choose **GET**, enter an endpoint such as `http://127.0.0.1:8000/news?skip=0&limit=20`, and send the request. For category labels with spaces, URL-encode the spaces or select the endpoint in Swagger UI. No request body or authentication is required by these project endpoints.

Invalid query values generally return `422`; malformed IDs or dates return `400`; a valid but missing record returns `404`; database operation failures return a safe `503` response. The health endpoint returns `{"status":"ok","database":"connected"}` when its MongoDB ping succeeds.

## Daily Scheduler Behavior

The scheduler starts and stops with the FastAPI application lifespan. During startup it prepares the MongoDB collections and indexes, then starts an `AsyncIOScheduler`. It uses `NEWS_SCHEDULE_HOUR`, `NEWS_SCHEDULE_MINUTE`, and `NEWS_SCHEDULE_TIMEZONE`; the template sets 06:00 in `Asia/Kolkata` (Indian Standard Time). This explicit time zone is used instead of assuming the computer's local time. Change the setting to another valid IANA name if appropriate.

The workflow does **not** run immediately at API startup. It waits for the next daily schedule time. Only one instance of the job can run at a time (`max_instances=1`); multiple due executions are coalesced, and an execution delayed by up to one hour is allowed. The scheduler is in memory, not a persistent job store. Runs missed while the API process is stopped are skipped rather than replayed after restart.

The standalone command `python .\scheduler.py` also runs a blocking scheduler independently of FastAPI. Avoid running it at the same time as the API scheduler, or the same work may run twice. To check workflow ordering safely without calling NewsAPI or writing to MongoDB, run:

```powershell
.\.venv\Scripts\python.exe .\scheduler.py --test
```

## Automated Tests

Run the complete automated suite from the project root when ready:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

The news-fetch and storage tests use mocks; API lifecycle and endpoint tests mock database and scheduler setup; briefing tests use mocked collections. The standalone database check is a separate command and uses the configured MongoDB server. Test results are not a substitute for a manual live API/NewsAPI check.

## Common Errors and Troubleshooting

- **MongoDB connection or startup failure:** Start MongoDB Community Server and verify `MONGODB_URI`, network access, and credentials. Startup deliberately fails if it cannot ping MongoDB and prepare indexes.
- **Index creation failure:** Confirm the database user can create indexes. If the collections already contain duplicate article URLs or briefing dates, resolve those duplicates before creating unique indexes.
- **NewsAPI key missing or rejected:** Set `NEWS_API_KEY` in `.env`, verify it is current, and check the provider account and service status. Never include the key in a bug report.
- **NewsAPI network or rate-limit error:** Check internet access and provider status/limits. The job reports safe error information and retries at a later scheduled run; it does not retry continuously.
- **No articles or briefing visible:** The job runs at its configured time, not immediately on startup. Verify the time zone, wait for the next run, then inspect `/news` and `/briefings`. An empty provider result may produce a briefing without news.
- **`Address already in use`:** Another process is using port `8000`. Stop that process or choose another Uvicorn port, such as `--port 8001`.
- **`ModuleNotFoundError`:** Activate `.venv` and run `python -m pip install -r requirements.txt` again.
- **API returns `503`:** Check MongoDB availability and the application log. API error responses avoid returning database connection details.
- **Duplicate records are skipped:** Repeated URLs are counted as duplicates, and unique indexes protect the database. Existing records are not updated.

## Manual End-of-Project Testing Checklist

- [ ] Install the dependencies in a fresh `.venv` and configure a private `.env`.
- [ ] Start MongoDB and confirm the standalone database/index check succeeds.
- [ ] Start the app using `.\.venv\Scripts\python.exe -m uvicorn api:app --reload`.
- [ ] Open `http://127.0.0.1:8000/` and confirm the TechPulse dashboard loads from the FastAPI server.
- [ ] Open `/docs` and call `/health`; confirm it reports a connected database.
- [ ] Confirm the connection badge changes to Connected only after a successful health response.
- [ ] Search by keyword, select a category, load more stories, open an article details dialog, and follow an original publisher link.
- [ ] Review the latest briefing and confirm only saved briefing fields are displayed.
- [ ] Call `/news`, `/news/search`, `/news/category/{category}`, `/news/{article_id}`, `/briefings`, and `/briefings/{YYYY-MM-DD}` using valid and invalid values.
- [ ] Confirm invalid values return expected errors and responses do not reveal credentials.
- [ ] Verify the configured schedule hour, minute, and IANA time zone; do not expect a workflow run immediately on startup.
- [ ] After the next scheduled run, inspect the stored articles and briefing; confirm article URLs/categories/scores and the briefing date/content.
- [ ] Stop the server with `Ctrl+C` and confirm shutdown completes cleanly.
- [ ] Run the automated suite shown above, then review `git status` to make sure `.env` and `.venv` are not staged.

## Beginner Viva / Interview Questions

1. **What does this project do?**

   It fetches technology news each day, validates and categorizes the articles, stores them in MongoDB, creates a briefing, and provides read-only API endpoints.

2. **What is FastAPI lifespan used for?**

   Lifespan runs setup when the API starts and cleanup when it stops. Here it prepares MongoDB and starts and shuts down the scheduler.

3. **How does APScheduler know when to run the workflow?**

   A cron-style daily trigger uses the configured hour, minute, and IANA time zone.

4. **How are duplicate articles prevented?**

   The application skips repeated URLs within one batch, and MongoDB's unique index on `news.url` prevents the same URL being stored again.

5. **What happens when the API is stopped at the scheduled time?**

   The scheduler is in memory, so a run missed while the process is stopped is skipped. It waits for the next scheduled time after restart.
