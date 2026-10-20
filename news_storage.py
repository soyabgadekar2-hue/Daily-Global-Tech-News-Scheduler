"""Categorize, validate, score, and save fetched news articles."""

import re
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from urllib.parse import urlsplit

from pymongo.errors import DuplicateKeyError

from database import prepare_collections


# Earlier entries win when an article matches multiple categories.
CATEGORY_KEYWORDS = (
    (
        "Agentic AI",
        ("agentic ai", "agentic", "ai agent", "ai agents", "autonomous agent"),
    ),
    (
        "Artificial Intelligence",
        (
            "artificial intelligence",
            "machine learning",
            "generative ai",
            "genai",
            "ai",
            "ml",
            "large language model",
            "llm",
            "deep learning",
            "neural network",
        ),
    ),
    (
        "Quantum Computing",
        ("quantum computing", "quantum computer", "quantum processor", "qubit"),
    ),
    (
        "Cloud Computing",
        (
            "cloud computing",
            "cloud platform",
            "cloud services",
            "kubernetes",
            "amazon web services",
            "aws",
            "google cloud",
            "gcp",
            "microsoft azure",
            "azure",
        ),
    ),
    (
        "Software Architecture",
        (
            "software architecture",
            "microservices",
            "software design",
            "distributed system",
            "system architecture",
        ),
    ),
    (
        "Cybersecurity",
        (
            "cybersecurity",
            "cyber security",
            "data breach",
            "ransomware",
            "vulnerability",
            "malware",
            "security patch",
        ),
    ),
    (
        "Programming and Developer Tools",
        (
            "programming",
            "developer tools",
            "programming language",
            "open source",
            "software development",
            "code editor",
            "github copilot",
        ),
    ),
    (
        "Startups and Tech Business",
        (
            "startup",
            "start-up",
            "venture capital",
            "funding round",
            "ipo",
            "acquisition",
            "tech business",
        ),
    ),
    (
        "Global Tech Companies and Trends",
        (
            "technology industry",
            "tech industry",
            "tech companies",
            "technology companies",
            "technology trend",
            "technology trends",
            "apple",
            "microsoft",
            "google",
            "amazon",
            "samsung",
            "meta",
        ),
    ),
)

_HEADLINE_SIGNALS = (
    "breakthrough",
    "launches",
    "announces",
    "raises",
    "acquisition",
    "security",
    "vulnerability",
    "release",
    "unveils",
    "funding",
    "research",
)


def categorize_article(article: Mapping[str, object]) -> str | None:
    """Return the first matching category, or None when no keywords match."""
    title = article.get("title")
    description = article.get("description")
    text = " ".join(
        value for value in (title, description) if isinstance(value, str)
    ).casefold()

    for category, keywords in CATEGORY_KEYWORDS:
        if any(
            re.search(r"\b" + re.escape(keyword) + r"\b", text)
            for keyword in keywords
        ):
            return category
    return None


def _is_valid_url(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False

    url = value.strip()
    if any(character.isspace() for character in url):
        return False

    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        parsed.port
        return True
    except ValueError:
        return False


def _published_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def calculate_importance_score(
    article: Mapping[str, object],
    now: datetime | None = None,
) -> int:
    """Score category relevance, headline signals, and publication recency (0-100)."""
    title = article.get("title")
    headline = title.casefold() if isinstance(title, str) else ""

    relevance_points = 40 if categorize_article(article) is not None else 15
    signal_count = sum(
        1 for signal in _HEADLINE_SIGNALS if signal in headline
    )
    headline_points = min(signal_count * 10, 30)

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    published_at = _published_datetime(article.get("published_at"))
    recency_points = 0
    if published_at is not None:
        age = current_time.astimezone(timezone.utc) - published_at
        if age.total_seconds() >= 0:
            if age.total_seconds() <= 24 * 60 * 60:
                recency_points = 30
            elif age.total_seconds() <= 7 * 24 * 60 * 60:
                recency_points = 20
            elif age.total_seconds() <= 30 * 24 * 60 * 60:
                recency_points = 10

    return relevance_points + headline_points + recency_points


def _prepare_article(
    article: object,
    fetched_at: datetime,
) -> dict[str, object] | None:
    if not isinstance(article, Mapping):
        return None

    title = article.get("title")
    url = article.get("url")
    if not isinstance(title, str) or not title.strip() or not _is_valid_url(url):
        return None

    source = article.get("source")
    published_at = article.get("published_at")
    description = article.get("description")
    prepared: dict[str, object] = {
        "title": title.strip(),
        "url": url.strip(),
        "source": source.strip() if isinstance(source, str) else None,
        "published_at": (
            published_at.strip() if isinstance(published_at, str) else None
        ),
        "description": (
            description.strip() if isinstance(description, str) else None
        ),
        "category": categorize_article(article),
        "fetched_at": fetched_at,
    }
    prepared["importance_score"] = calculate_importance_score(prepared, fetched_at)
    return prepared


def save_articles(
    articles: Iterable[object],
    collection=None,
) -> dict[str, int]:
    """Validate and insert articles; count invalid and duplicate URLs without failing."""
    if collection is None:
        collection, _ = prepare_collections()

    counts = {"inserted": 0, "duplicates": 0, "rejected": 0}
    seen_urls = set()
    fetched_at = datetime.now(timezone.utc)

    for article in articles:
        prepared = _prepare_article(article, fetched_at)
        if prepared is None:
            counts["rejected"] += 1
            continue

        url = prepared["url"]
        if url in seen_urls:
            counts["duplicates"] += 1
            continue
        seen_urls.add(url)

        try:
            collection.insert_one(prepared)
        except DuplicateKeyError:
            counts["duplicates"] += 1
        else:
            counts["inserted"] += 1

    return counts
