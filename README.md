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

The local `.env` file contains MongoDB, news provider, schedule, and fetch-limit settings. It is ignored by Git. Use `.env.example` as the safe template; add a news API key and base URL only after choosing a provider. `config.py` loads these values with beginner-friendly defaults.

## Project Status

Step 2, environment and configuration, is complete. The virtual environment, dependency installation, and configuration defaults were verified successfully.

## Future Stages

1. Choose a news provider and retrieve articles.
2. Categorize news and store it in MongoDB.
3. Generate daily briefings.
4. Schedule the daily workflow.
5. Expose REST APIs with FastAPI.