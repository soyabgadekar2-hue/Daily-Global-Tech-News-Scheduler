import os

from dotenv import load_dotenv

# Load local settings from the project's .env file.
load_dotenv()

# Use safe defaults so the project can start before a news provider is chosen.
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DATABASE_NAME = os.getenv("DATABASE_NAME", "tech_news")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
NEWS_API_BASE_URL = os.getenv("NEWS_API_BASE_URL", "")
NEWS_SCHEDULE_HOUR = int(os.getenv("NEWS_SCHEDULE_HOUR", "6"))
NEWS_SCHEDULE_MINUTE = int(os.getenv("NEWS_SCHEDULE_MINUTE", "0"))
NEWS_FETCH_LIMIT = int(os.getenv("NEWS_FETCH_LIMIT", "100"))
