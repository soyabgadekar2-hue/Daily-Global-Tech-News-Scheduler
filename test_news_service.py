import unittest
from unittest.mock import Mock, patch

import requests

from news_service import NewsServiceError, fetch_technology_news


class NewsServiceTests(unittest.TestCase):
    def setUp(self):
        self.settings = patch.multiple(
            "news_service.config",
            NEWS_API_KEY="mock-api-key",
            NEWS_API_BASE_URL="https://newsapi.org/v2",
        )
        self.settings.start()
        self.addCleanup(self.settings.stop)
        self.response = Mock()
        self.response.status_code = 200

    def test_fetches_and_normalizes_articles(self):
        self.response.json.return_value = {
            "status": "ok",
            "articles": [
                {
                    "title": "  New technology  ",
                    "url": " https://example.com/story ",
                    "source": {"name": " Example News "},
                    "publishedAt": "2026-10-20T12:00:00Z",
                    "description": "  A technology story. ",
                },
                {"title": "Title and URL are enough", "url": "https://example.com/2"},
            ],
        }

        with patch("news_service.requests.get", return_value=self.response) as get:
            articles = fetch_technology_news(limit=5, timeout=3)

        self.assertEqual(
            articles,
            [
                {
                    "title": "New technology",
                    "url": "https://example.com/story",
                    "source": "Example News",
                    "published_at": "2026-10-20T12:00:00Z",
                    "description": "A technology story.",
                },
                {
                    "title": "Title and URL are enough",
                    "url": "https://example.com/2",
                    "source": None,
                    "published_at": None,
                    "description": None,
                },
            ],
        )
        get.assert_called_once_with(
            "https://newsapi.org/v2/everything",
            headers={"X-Api-Key": "mock-api-key"},
            params={"q": "technology", "sortBy": "publishedAt", "pageSize": 5},
            timeout=3,
        )

    def test_empty_article_list_returns_empty_list(self):
        self.response.json.return_value = {"status": "ok", "articles": []}

        with patch("news_service.requests.get", return_value=self.response):
            self.assertEqual(fetch_technology_news(), [])

    def test_invalid_json_raises_clear_error(self):
        self.response.json.side_effect = ValueError("invalid JSON")

        with patch("news_service.requests.get", return_value=self.response):
            with self.assertRaisesRegex(NewsServiceError, "invalid JSON"):
                fetch_technology_news()

    def test_timeout_raises_clear_error(self):
        with patch(
            "news_service.requests.get",
            side_effect=requests.Timeout("private details"),
        ):
            with self.assertRaisesRegex(NewsServiceError, "timed out") as error:
                fetch_technology_news(timeout=2)

        self.assertNotIn("private details", str(error.exception))

    def test_connection_failure_raises_clear_error(self):
        with patch(
            "news_service.requests.get",
            side_effect=requests.ConnectionError("private details"),
        ):
            with self.assertRaisesRegex(NewsServiceError, "Could not connect") as error:
                fetch_technology_news()

        self.assertNotIn("private details", str(error.exception))

    def test_http_error_raises_clear_error_without_response_body(self):
        self.response.status_code = 401
        with patch("news_service.requests.get", return_value=self.response):
            with self.assertRaisesRegex(NewsServiceError, "HTTP 401"):
                fetch_technology_news()

    def test_unexpected_article_structure_raises_clear_error(self):
        self.response.json.return_value = {"status": "ok", "articles": None}

        with patch("news_service.requests.get", return_value=self.response):
            with self.assertRaisesRegex(NewsServiceError, "articles list"):
                fetch_technology_news()

    def test_articles_missing_title_or_url_are_skipped(self):
        self.response.json.return_value = {
            "status": "ok",
            "articles": [
                {"title": "No URL"},
                {"url": "https://example.com/no-title"},
                {"title": "Valid", "url": "https://example.com/valid"},
            ],
        }

        with patch("news_service.requests.get", return_value=self.response):
            articles = fetch_technology_news()

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "Valid")


if __name__ == "__main__":
    unittest.main()
