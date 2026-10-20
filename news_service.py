"""Fetch and normalize technology articles from NewsAPI.org."""

import requests

import config


class NewsServiceError(Exception):
    """Raised when NewsAPI cannot provide a usable response."""


def fetch_technology_news(
    limit: int = config.NEWS_FETCH_LIMIT,
    timeout: float = 10.0,
) -> list[dict[str, str | None]]:
    """Fetch recent technology articles without saving them to MongoDB."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100.")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or timeout <= 0
    ):
        raise ValueError("timeout must be a positive number of seconds.")

    api_key = config.NEWS_API_KEY.strip()
    base_url = config.NEWS_API_BASE_URL.strip().rstrip("/")
    if not api_key:
        raise NewsServiceError("NEWS_API_KEY is not configured in .env.")
    if not base_url:
        raise NewsServiceError("NEWS_API_BASE_URL is not configured in .env.")

    try:
        response = requests.get(
            f"{base_url}/everything",
            headers={"X-Api-Key": api_key},
            params={
                "q": "technology",
                "sortBy": "publishedAt",
                "pageSize": limit,
            },
            timeout=timeout,
        )
    except requests.Timeout as error:
        raise NewsServiceError(
            f"NewsAPI request timed out after {timeout} seconds."
        ) from error
    except requests.RequestException as error:
        raise NewsServiceError(
            "Could not connect to NewsAPI. Check the network and try again."
        ) from error

    if response.status_code != 200:
        raise NewsServiceError(
            f"NewsAPI returned HTTP {response.status_code}. "
            "Check the API key, request settings, and provider status."
        )

    try:
        payload = response.json()
    except ValueError as error:
        raise NewsServiceError("NewsAPI returned invalid JSON.") from error

    if not isinstance(payload, dict):
        raise NewsServiceError("NewsAPI returned an unexpected response format.")
    if payload.get("status") != "ok":
        raise NewsServiceError("NewsAPI reported an error in its JSON response.")

    articles = payload.get("articles")
    if not isinstance(articles, list):
        raise NewsServiceError(
            "NewsAPI response is missing the expected articles list."
        )

    normalized_articles = []
    for article in articles[:limit]:
        if not isinstance(article, dict):
            continue

        title = article.get("title")
        url = article.get("url")
        if not isinstance(title, str) or not title.strip():
            continue
        if not isinstance(url, str) or not url.strip():
            continue

        source = article.get("source")
        if isinstance(source, dict):
            source = source.get("name")
        elif not isinstance(source, str):
            source = None

        published_at = article.get("publishedAt")
        description = article.get("description")

        normalized_articles.append(
            {
                "title": title.strip(),
                "url": url.strip(),
                "source": source.strip() if isinstance(source, str) else None,
                "published_at": (
                    published_at.strip()
                    if isinstance(published_at, str)
                    else None
                ),
                "description": (
                    description.strip() if isinstance(description, str) else None
                ),
            }
        )

    return normalized_articles
