# Daily-Global-Tech-News-Scheduler

## Objective

Collect global technology news each day, categorize and store it in MongoDB, create daily briefings, and make the information available through REST APIs.

## Technology Stack

Python, MongoDB, Requests, PyMongo, python-dotenv, APScheduler, FastAPI, and Uvicorn.

## Environment Setup

Create and activate the virtual environment in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the project dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Environment Configuration

The local `.env` file contains MongoDB, news provider, schedule, and fetch-limit settings. It is ignored by Git. Use `.env.example` as the safe template, and keep your API key only in `.env`. `config.py` loads these values with beginner-friendly defaults.

## Step 3: MongoDB Connection

`database.py` reuses a PyMongo client, checks the server with `ping`, and prepares the `news` and `daily_briefings` collections. It adds unique indexes to `news.url` and `daily_briefings.briefing_date`. The database test checks these indexes without inserting news or briefing documents.

Make sure the local MongoDB Community Server is running, activate `.venv`, then run:

```powershell
python .\test_database.py
```

A successful test prints the ping status, database name, collections, and unique indexes. If it fails, check the MongoDB service and port `27017`, then review the `MONGODB_URI` and database permissions in `.env`.

## Project Status

Step 2, environment and configuration, is complete. The virtual environment, dependency installation, and configuration defaults were verified successfully. Step 3, MongoDB connection and index setup, is complete; `python .\test_database.py` passed against the local MongoDB server.

## Step 4: Fetch Technology News

This step uses [NewsAPI.org](https://newsapi.org/docs) and its Everything endpoint. Copy `.env.example` to `.env` if needed, then set `NEWS_API_KEY` to the key from your NewsAPI account and `NEWS_API_BASE_URL` to `https://newsapi.org/v2`. Keep the key private; do not paste it into source code or share it in chat. `NEWS_FETCH_LIMIT` controls the result count and must be between 1 and 100.

`news_service.py` sends a GET request to `/everything`, passes `technology` as the search term, and puts the key in the `X-Api-Key` request header. Requests time out after 10 seconds by default; callers can choose a different timeout. The function returns normalized article dictionaries and does not write to MongoDB.

A REST API lets one program ask another for information using web requests. An HTTP request is the message sent to the service; an HTTP response is its reply. A JSON response is structured text that Python can turn into dictionaries and lists. An API key identifies the application making the request. HTTP status codes summarize the result: `200` means success, `401` commonly indicates an authentication problem, and `429` means the service is limiting requests. A timeout puts a limit on how long the program waits before reporting that the service did not respond in time.

Run the mocked tests from PowerShell with the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe .\test_news_service.py
```

Expected result:

```text
........
----------------------------------------------------------------------
Ran 8 tests in ...s

OK
```

These tests replace the HTTP request with mocked responses. They do not use your API key or contact NewsAPI.org, so passing them is not a live API verification. No Step 4 command is provided for live fetching; this stage only validates the fetch service with safe mocked tests.

## Step 5: Categorize and Save News

`news_storage.py` categorizes each article by matching keywords in its title and description, validates the required title and URL, calculates a transparent importance score, and inserts valid articles into MongoDB's `news` collection. The categories are Artificial Intelligence, Agentic AI, Quantum Computing, Cloud Computing, Software Architecture, Cybersecurity, Programming and Developer Tools, Startups and Tech Business, and Global Tech Companies and Trends. When several keyword groups match, the first matching category in the list in `news_storage.py` is selected. Articles without a category keyword get `category: None`.

The score is a simple indicator, not an objective measure of truth: categorized articles receive 40 relevance points (uncategorized articles receive 15), up to 30 points for headline signals, and up to 30 points for recency (within one day, seven days, or 30 days). Invalid or future publication dates earn no recency points. Each saved article also gets a UTC `fetched_at` timestamp. Invalid titles or URLs are rejected. URLs must use HTTP or HTTPS and include a host.

MongoDB's existing unique index on `news.url` prevents storing the same URL twice. Duplicate URLs in a batch are skipped, and MongoDB duplicate-key errors are counted rather than raised. The function reports the numbers inserted, duplicated, and rejected; it does not delete or update existing records.

Run the Step 5 tests from PowerShell with the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe .\test_news_storage.py
```

Expected result:

```text
..........
----------------------------------------------------------------------
Ran 10 tests in ...s

OK
```

The tests pass a mocked collection to the save function, so they do not write to MongoDB. To run the Step 4 and Step 5 tests together, use:

```powershell
.\.venv\Scripts\python.exe -m unittest .\test_news_service.py .\test_news_storage.py
```

The combined run should report 18 tests and `OK`.

## Step 6: Generate the Daily Briefing

A daily briefing is a date-specific digest built from articles already stored in MongoDB. `briefing_service.py` sorts stored articles by importance score and publication date, then selects from categories in rounds so lower-ranked categories can be represented when the article limit allows. It groups the selected articles by category and includes title, URL, source, publication date, and a short extractive summary. When an article has no description, the briefing says the available description is limited instead of making up a summary.

The "why it matters" text, Learning of the Day, and Career Opportunity are labeled generated suggestions rather than facts reported by articles or job listings. No paid AI service is used. If there are no stored articles, the briefing contains an empty news mapping and says that no suggestions could be generated.

Briefings use a UTC date string (`YYYY-MM-DD`) and the existing unique index on `daily_briefings.briefing_date`. The first briefing for a date is preserved on reruns; it is not replaced. If two runs race to create the same date, the one that encounters a duplicate-key error loads the already-saved briefing. MongoDB `ObjectId` and datetime values are converted to strings in the returned result for JSON serialization, while MongoDB stores its native values.

Run the Step 6 tests from PowerShell using the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m unittest test_briefing_service
```

Expected output:

```text
......
----------------------------------------------------------------------
Ran 6 tests in ...s

OK
```

Run all mocked API, storage, and briefing tests together:

```powershell
.\.venv\Scripts\python.exe -m unittest test_news_service test_news_storage test_briefing_service
```

The combined run should report 24 tests and `OK`. Tests use mocked collections and do not call NewsAPI or modify real database records.

## Future Stages

1. Schedule the daily workflow.
2. Expose REST APIs with FastAPI.