"""Build and store a daily briefing from articles already in MongoDB."""

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from database import prepare_collections
from news_storage import calculate_importance_score, categorize_article


DEFAULT_ARTICLE_LIMIT = 15

_CATEGORY_SUGGESTIONS = {
    "Artificial Intelligence": (
        "Explore how machine-learning systems are trained and evaluated."
    ),
    "Agentic AI": "Explore how AI agents plan tasks and use tools.",
    "Quantum Computing": (
        "Learn how qubits differ from the bits used in classical computers."
    ),
    "Cloud Computing": "Explore how cloud services provide computing resources.",
    "Software Architecture": (
        "Study how software components are organized and communicate."
    ),
    "Cybersecurity": "Review practical ways to identify and reduce security risks.",
    "Programming and Developer Tools": (
        "Try a programming tool or language mentioned in the article."
    ),
    "Startups and Tech Business": (
        "Explore how technology companies develop and fund products."
    ),
    "Global Tech Companies and Trends": (
        "Compare how technology companies respond to industry changes."
    ),
    "Uncategorized": "Choose a technology topic from today's article descriptions.",
}


def _json_value(value: Any) -> Any:
    """Convert MongoDB values and nested containers into JSON-friendly values."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _parse_published_at(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _article_rank(article: dict[str, Any]) -> tuple[float, float]:
    score = article.get("importance_score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        score = calculate_importance_score(article)

    published_at = _parse_published_at(article.get("published_at"))
    published_timestamp = published_at.timestamp() if published_at else 0.0
    return float(score), published_timestamp


def _summary(description: Any) -> str:
    if not isinstance(description, str) or not description.strip():
        return "Available description is limited; no summary can be made."

    text = " ".join(description.split())
    sentence_end = next(
        (index for index, character in enumerate(text) if character in ".!?"),
        None,
    )
    if sentence_end is not None:
        text = text[: sentence_end + 1]
    if len(text) > 280:
        text = text[:277].rsplit(" ", 1)[0] + "..."
    return text


def _why_it_matters(category: str) -> str:
    suggestion = _CATEGORY_SUGGESTIONS.get(
        category, _CATEGORY_SUGGESTIONS["Uncategorized"]
    )
    return f"Generated suggestion, not a reported fact: {suggestion}"


def _prepare_briefing_article(article: dict[str, Any]) -> dict[str, Any]:
    category = article.get("category")
    if not isinstance(category, str) or not category.strip():
        category = categorize_article(article) or "Uncategorized"

    return {
        "title": article.get("title"),
        "url": article.get("url"),
        "source": article.get("source"),
        "published_at": article.get("published_at"),
        "summary": _summary(article.get("description")),
        "why_it_matters": _why_it_matters(category),
    }


def _select_diverse_articles(
    articles: list[dict[str, Any]],
    limit: int,
) -> list[tuple[str, dict[str, Any]]]:
    ranked = sorted(articles, key=_article_rank, reverse=True)
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for article in ranked:
        category = article.get("category")
        if not isinstance(category, str) or not category.strip():
            category = categorize_article(article) or "Uncategorized"
        by_category[category].append(article)

    categories = list(by_category)
    selected: list[tuple[str, dict[str, Any]]] = []
    while categories and len(selected) < limit:
        remaining_categories = []
        for category in categories:
            selected.append((category, by_category[category].pop(0)))
            if by_category[category]:
                remaining_categories.append(category)
            if len(selected) == limit:
                break
        categories = remaining_categories
    return selected


def generate_daily_briefing(
    briefing_date: date | None = None,
    article_limit: int = DEFAULT_ARTICLE_LIMIT,
    news_collection=None,
    briefings_collection=None,
) -> dict[str, Any]:
    """Create today's briefing once; later runs preserve the stored briefing."""
    if (
        isinstance(article_limit, bool)
        or not isinstance(article_limit, int)
        or article_limit < 1
    ):
        raise ValueError("article_limit must be a positive integer.")
    if briefing_date is None:
        briefing_date = datetime.now(timezone.utc).date()
    if isinstance(briefing_date, datetime):
        briefing_date = briefing_date.date()
    if not isinstance(briefing_date, date):
        raise ValueError("briefing_date must be a date.")

    if news_collection is None or briefings_collection is None:
        prepared_news, prepared_briefings = prepare_collections()
        if news_collection is None:
            news_collection = prepared_news
        if briefings_collection is None:
            briefings_collection = prepared_briefings

    date_key = briefing_date.isoformat()
    existing = briefings_collection.find_one({"briefing_date": date_key})
    if existing is not None:
        return _json_value(existing)

    articles = list(news_collection.find({}))
    selected = _select_diverse_articles(articles, article_limit)
    grouped_news: dict[str, list[dict[str, Any]]] = {}
    for category, article in selected:
        grouped_news.setdefault(category, []).append(_prepare_briefing_article(article))

    if selected:
        lead_category = selected[0][0]
        learning = {
            "type": "generated_suggestion",
            "text": _CATEGORY_SUGGESTIONS.get(
                lead_category, _CATEGORY_SUGGESTIONS["Uncategorized"]
            ),
        }
        career = {
            "type": "generated_suggestion",
            "text": (
                f"Consider exploring roles related to {lead_category}. "
                "This is a general suggestion, not a job listing."
            ),
        }
    else:
        learning = {
            "type": "generated_suggestion",
            "text": "No articles are available today, so no topic suggestion was generated.",
        }
        career = {
            "type": "generated_suggestion",
            "text": "No articles are available today, so no career suggestion was generated.",
        }

    briefing = {
        "briefing_date": date_key,
        "news": grouped_news,
        "learning_of_the_day": learning,
        "career_opportunity": career,
        "created_at": datetime.now(timezone.utc),
    }

    try:
        result = briefings_collection.insert_one(briefing)
    except DuplicateKeyError:
        existing = briefings_collection.find_one({"briefing_date": date_key})
        if existing is None:
            raise
        return _json_value(existing)

    briefing["_id"] = result.inserted_id
    return _json_value(briefing)
