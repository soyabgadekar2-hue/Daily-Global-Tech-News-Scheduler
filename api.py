"""Read-only REST API for stored technology news and daily briefings."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import logging
import re
from datetime import date, datetime
from pathlib import Path as FilePath

from bson import ObjectId
from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pymongo.errors import PyMongoError

import config
from database import connect_to_mongodb, prepare_collections
from scheduler import create_api_scheduler


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Prepare MongoDB and run one daily scheduler for this application process."""
    if (
        getattr(application.state, "scheduler_starting", False)
        or getattr(application.state, "scheduler", None) is not None
    ):
        logger.warning("Scheduler startup was requested more than once.")
        raise RuntimeError("The application scheduler is already active.")

    application.state.scheduler_starting = True
    scheduler = None
    try:
        logger.info("Preparing MongoDB collections and indexes.")
        prepare_collections()
        scheduler = create_api_scheduler()
        scheduler.start()
        application.state.scheduler = scheduler
    except Exception as error:
        if scheduler is not None and scheduler.running:
            try:
                scheduler.shutdown(wait=False)
            except Exception as shutdown_error:
                logger.error(
                    "Scheduler cleanup after startup failure failed (%s).",
                    type(shutdown_error).__name__,
                )
        application.state.scheduler = None
        application.state.scheduler_starting = False
        logger.error("Application startup failed (%s).", type(error).__name__)
        raise

    application.state.scheduler_starting = False
    logger.info(
        "Daily news scheduler started for %02d:%02d (%s).",
        config.NEWS_SCHEDULE_HOUR,
        config.NEWS_SCHEDULE_MINUTE,
        config.NEWS_SCHEDULE_TIMEZONE,
    )
    try:
        yield
    finally:
        try:
            if scheduler.running:
                scheduler.shutdown(wait=False)
            logger.info("Daily news scheduler stopped.")
        except Exception as error:
            logger.error("Scheduler shutdown failed (%s).", type(error).__name__)
            raise
        finally:
            application.state.scheduler = None
            application.state.scheduler_starting = False


app = FastAPI(
    title="Daily Global Tech News API",
    description="Read stored technology news articles and daily briefings.",
    version="1.0.0",
    lifespan=lifespan,
)


def _json_value(value):
    """Convert MongoDB IDs and Python date values to JSON-friendly values."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _collection(name: str):
    database = connect_to_mongodb()
    return database[name]


def _list_documents(collection_name: str, query: dict, skip: int, limit: int):
    collection = _collection(collection_name)
    cursor = (
        collection.find(query)
        .sort([("fetched_at", -1), ("_id", -1)])
        .skip(skip)
        .limit(limit)
    )
    return {
        "items": [_json_value(document) for document in cursor],
        "skip": skip,
        "limit": limit,
        "total": collection.count_documents(query),
    }


@app.exception_handler(ConnectionError)
def handle_database_connection_error(request, error):
    logger.error("Database connection failed (%s).", type(error).__name__)
    return JSONResponse(
        status_code=503,
        content={"detail": "Database is unavailable. Try again later."},
    )


@app.exception_handler(PyMongoError)
def handle_database_operation_error(request, error):
    logger.error("Database operation failed (%s).", type(error).__name__)
    return JSONResponse(
        status_code=503,
        content={"detail": "Database operation failed. Try again later."},
    )


@app.exception_handler(Exception)
def handle_unexpected_error(request, error):
    logger.error("API request failed unexpectedly (%s).", type(error).__name__)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred."},
    )


@app.get("/health")
def health_check():
    """Check application availability and the existing MongoDB ping."""
    _collection("news")
    return {"status": "ok", "database": "connected"}


@app.get("/news")
def list_news(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    """List stored news with bounded pagination."""
    return _list_documents("news", {}, skip, limit)


@app.get("/news/search")
def search_news(
    keyword: str = Query(min_length=1, max_length=100),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Search titles and descriptions using a literal, case-insensitive keyword."""
    keyword = keyword.strip()
    if not keyword:
        raise HTTPException(status_code=422, detail="keyword must not be blank.")

    literal_keyword = re.escape(keyword)
    query = {
        "$or": [
            {"title": {"$regex": literal_keyword, "$options": "i"}},
            {"description": {"$regex": literal_keyword, "$options": "i"}},
        ]
    }
    return _list_documents("news", query, skip, limit)


@app.get("/news/category/{category}")
def list_news_by_category(
    category: str = Path(min_length=1, max_length=100),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    """List stored news matching a category label."""
    category = category.strip()
    if not category:
        raise HTTPException(status_code=422, detail="category must not be blank.")
    return _list_documents("news", {"category": category}, skip, limit)


@app.get("/news/{article_id}")
def get_news_article(article_id: str):
    """Retrieve one article by its MongoDB ObjectId."""
    if not ObjectId.is_valid(article_id):
        raise HTTPException(status_code=400, detail="Invalid article ID.")

    article = _collection("news").find_one({"_id": ObjectId(article_id)})
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found.")
    return _json_value(article)


@app.get("/briefings")
def list_briefings(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    """List stored daily briefings with bounded pagination."""
    collection = _collection("daily_briefings")
    cursor = (
        collection.find({})
        .sort([("briefing_date", -1), ("_id", -1)])
        .skip(skip)
        .limit(limit)
    )
    return {
        "items": [_json_value(document) for document in cursor],
        "skip": skip,
        "limit": limit,
        "total": collection.count_documents({}),
    }


@app.get("/briefings/{briefing_date}")
def get_briefing(briefing_date: str):
    """Retrieve a briefing using the YYYY-MM-DD date format."""
    try:
        parsed_date = datetime.strptime(briefing_date, "%Y-%m-%d").date()
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail="Invalid briefing date. Use YYYY-MM-DD.",
        ) from error
    if parsed_date.isoformat() != briefing_date:
        raise HTTPException(
            status_code=400,
            detail="Invalid briefing date. Use YYYY-MM-DD.",
        )

    briefing = _collection("daily_briefings").find_one(
        {"briefing_date": parsed_date.isoformat()}
    )
    if briefing is None:
        raise HTTPException(status_code=404, detail="Briefing not found.")
    return _json_value(briefing)


app.mount(
    "/",
    StaticFiles(directory=FilePath(__file__).resolve().parent / "frontend", html=True),
    name="frontend",
)
