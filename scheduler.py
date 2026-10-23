"""Run the daily fetch, storage, and briefing workflow."""

import argparse
import logging
from collections.abc import Callable
from datetime import date, datetime
from typing import Any, TypeVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from apscheduler.events import EVENT_JOB_ERROR, JobExecutionEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from pymongo.errors import PyMongoError

import config
from briefing_service import generate_daily_briefing
from news_service import NewsServiceError, fetch_technology_news
from news_storage import save_articles


logger = logging.getLogger(__name__)

Article = dict[str, str | None]
Fetcher = Callable[[], list[Article]]
Saver = Callable[[list[Article]], dict[str, int]]
BriefingGenerator = Callable[[date], dict[str, Any]]
SchedulerType = TypeVar("SchedulerType", bound=BaseScheduler)


def _configured_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(config.NEWS_SCHEDULE_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError(
            "NEWS_SCHEDULE_TIMEZONE must be a valid IANA time-zone name, "
            "for example Asia/Kolkata."
        ) from error


def run_daily_workflow(
    *,
    fetcher: Fetcher | None = None,
    saver: Saver | None = None,
    briefing_generator: BriefingGenerator | None = None,
) -> bool:
    """Run fetch, save, and briefing steps in order; return success status."""
    if fetcher is None:
        fetcher = fetch_technology_news
    if saver is None:
        saver = save_articles
    if briefing_generator is None:
        briefing_generator = generate_daily_briefing

    try:
        articles = fetcher()
    except (NewsServiceError, requests.RequestException, ValueError) as error:
        logger.error(
            "News fetch failed (%s). Check the provider settings and network.",
            type(error).__name__,
        )
        return False

    logger.info("Fetched %d news articles.", len(articles))

    try:
        counts = saver(articles)
    except (ConnectionError, RuntimeError, PyMongoError) as error:
        logger.error(
            "Saving news failed (%s). Check MongoDB availability and permissions.",
            type(error).__name__,
        )
        return False

    logger.info(
        "News storage finished: %d inserted, %d duplicates, %d rejected.",
        counts.get("inserted", 0),
        counts.get("duplicates", 0),
        counts.get("rejected", 0),
    )

    try:
        local_briefing_date = datetime.now(_configured_timezone()).date()
        briefing = briefing_generator(local_briefing_date)
    except (ConnectionError, RuntimeError, PyMongoError, ValueError) as error:
        logger.error(
            "Daily briefing generation failed (%s). Check MongoDB and stored news.",
            type(error).__name__,
        )
        return False

    logger.info(
        "Daily briefing is ready for %s.",
        briefing.get("briefing_date", "the configured date"),
    )
    return True


def run_scheduled_workflow() -> None:
    """Run the workflow without exposing unexpected exception details to APScheduler."""
    try:
        run_daily_workflow()
    except Exception as error:
        logger.error(
            "Daily news workflow failed unexpectedly (%s).",
            type(error).__name__,
        )


def run_test_mode() -> bool:
    """Exercise workflow order with in-memory stand-ins and no network or database."""
    calls = []
    sample_articles: list[Article] = [
        {
            "title": "Scheduler test article",
            "url": "https://example.invalid/test",
            "source": "Local test only",
            "published_at": None,
            "description": None,
        }
    ]

    def fake_fetcher() -> list[Article]:
        calls.append("fetch")
        return sample_articles

    def fake_saver(articles: list[Article]) -> dict[str, int]:
        calls.append("save")
        if articles != sample_articles:
            raise AssertionError("Test workflow passed unexpected articles.")
        return {"inserted": 1, "duplicates": 0, "rejected": 0}

    def fake_briefing_generator(briefing_date: date) -> dict[str, Any]:
        calls.append("briefing")
        return {"briefing_date": briefing_date.isoformat()}

    succeeded = run_daily_workflow(
        fetcher=fake_fetcher,
        saver=fake_saver,
        briefing_generator=fake_briefing_generator,
    )
    if not succeeded or calls != ["fetch", "save", "briefing"]:
        logger.error("Scheduler test mode failed to verify the workflow order.")
        return False

    logger.info(
        "Scheduler test mode passed: fetch -> save -> briefing. "
        "No network request or database write was made."
    )
    return True


def _add_daily_job(
    scheduler: SchedulerType,
    timezone: ZoneInfo,
) -> SchedulerType:
    hour = config.NEWS_SCHEDULE_HOUR
    minute = config.NEWS_SCHEDULE_MINUTE
    if not 0 <= hour <= 23:
        raise ValueError("NEWS_SCHEDULE_HOUR must be between 0 and 23.")
    if not 0 <= minute <= 59:
        raise ValueError("NEWS_SCHEDULE_MINUTE must be between 0 and 59.")

    trigger = CronTrigger(hour=hour, minute=minute, timezone=timezone)
    scheduler.add_job(
        run_scheduled_workflow,
        trigger=trigger,
        id="daily_tech_news_workflow",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60 * 60,
    )
    return scheduler


def create_scheduler() -> BlockingScheduler:
    """Create (but do not start) the daily blocking scheduler."""
    timezone = _configured_timezone()
    return _add_daily_job(BlockingScheduler(timezone=timezone), timezone)


def _log_job_failure(event: JobExecutionEvent) -> None:
    """Log scheduled-job failures without exposing exception messages."""
    error_type = (
        type(event.exception).__name__
        if event.exception is not None
        else "unknown"
    )
    logger.error(
        "Scheduled job '%s' failed (%s).",
        event.job_id,
        error_type,
    )


def create_api_scheduler() -> AsyncIOScheduler:
    """Create (but do not start) the scheduler used by FastAPI."""
    timezone = _configured_timezone()
    scheduler = _add_daily_job(AsyncIOScheduler(timezone=timezone), timezone)
    scheduler.add_listener(_log_job_failure, EVENT_JOB_ERROR)
    return scheduler


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the daily tech news scheduler.")
    parser.add_argument(
        "--test",
        action="store_true",
        help="verify workflow order without network or database access",
    )
    arguments = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if arguments.test:
        return 0 if run_test_mode() else 1

    try:
        scheduler = create_scheduler()
    except ValueError as error:
        logger.error("%s", error)
        return 1

    timezone = config.NEWS_SCHEDULE_TIMEZONE
    logger.info(
        "Starting daily tech news scheduler for %02d:%02d (%s). "
        "Keep this process running.",
        config.NEWS_SCHEDULE_HOUR,
        config.NEWS_SCHEDULE_MINUTE,
        timezone,
    )
    try:
        scheduler.start()
    except KeyboardInterrupt:
        scheduler.shutdown(wait=False)
        logger.info("Daily tech news scheduler stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
