import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from pymongo.errors import DuplicateKeyError

from news_storage import (
    calculate_importance_score,
    categorize_article,
    save_articles,
)


class NewsStorageTests(unittest.TestCase):
    def test_categorizes_keywords_from_title_and_description(self):
        self.assertEqual(
            categorize_article({"title": "New AI agent", "description": ""}),
            "Agentic AI",
        )
        self.assertEqual(
            categorize_article(
                {
                    "title": "New research",
                    "description": "Quantum computing advances",
                }
            ),
            "Quantum Computing",
        )

    def test_categorizes_all_supported_categories(self):
        examples = (
            ("Artificial intelligence research", "Artificial Intelligence"),
            ("Quantum computing", "Quantum Computing"),
            ("Cloud computing", "Cloud Computing"),
            ("Software architecture", "Software Architecture"),
            ("Cybersecurity", "Cybersecurity"),
            ("Programming language", "Programming and Developer Tools"),
            ("Startup funding round", "Startups and Tech Business"),
            ("Technology industry", "Global Tech Companies and Trends"),
        )
        for title, expected_category in examples:
            with self.subTest(title=title):
                self.assertEqual(
                    categorize_article({"title": title}),
                    expected_category,
                )

    def test_first_category_wins_when_multiple_match(self):
        self.assertEqual(
            categorize_article(
                {"title": "Agentic AI startup raises funding round"}
            ),
            "Agentic AI",
        )

    def test_uncategorized_article_returns_none(self):
        self.assertIsNone(
            categorize_article({"title": "A general technology story"})
        )

    def test_rejects_missing_title_and_invalid_urls(self):
        collection = Mock()
        counts = save_articles(
            [
                {"url": "https://example.com/no-title"},
                {"title": "No URL"},
                {"title": "Bad scheme", "url": "ftp://example.com/story"},
                {"title": "Missing host", "url": "https:///story"},
                {"title": "Whitespace URL", "url": "https://example.com/a b"},
                {"title": "Bad port", "url": "https://example.com:invalid/story"},
            ],
            collection=collection,
        )

        self.assertEqual(counts, {"inserted": 0, "duplicates": 0, "rejected": 6})
        collection.insert_one.assert_not_called()

    def test_inserts_valid_article_with_metadata(self):
        collection = Mock()
        counts = save_articles(
            [
                {
                    "title": "New cybersecurity research breakthrough",
                    "url": "https://example.com/security",
                    "source": "Example News",
                    "published_at": "2026-10-20T11:00:00Z",
                    "description": "A security breakthrough.",
                }
            ],
            collection=collection,
        )

        self.assertEqual(counts, {"inserted": 1, "duplicates": 0, "rejected": 0})
        saved = collection.insert_one.call_args.args[0]
        self.assertEqual(saved["category"], "Cybersecurity")
        self.assertIsInstance(saved["fetched_at"], datetime)
        self.assertGreaterEqual(saved["importance_score"], 40)
        self.assertLessEqual(saved["importance_score"], 100)

    def test_skips_duplicate_urls_in_batch(self):
        collection = Mock()
        article = {"title": "Cloud platform update", "url": "https://example.com/1"}

        counts = save_articles([article, article], collection=collection)

        self.assertEqual(counts, {"inserted": 1, "duplicates": 1, "rejected": 0})
        collection.insert_one.assert_called_once()

    def test_handles_database_duplicate_key_error(self):
        collection = Mock()
        collection.insert_one.side_effect = DuplicateKeyError("existing URL")

        counts = save_articles(
            [{"title": "Cloud platform update", "url": "https://example.com/1"}],
            collection=collection,
        )

        self.assertEqual(counts, {"inserted": 0, "duplicates": 1, "rejected": 0})

    def test_importance_score_rewards_signals_and_recent_publication(self):
        now = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
        plain = {
            "title": "Cloud computing update",
            "published_at": (now - timedelta(days=60)).isoformat(),
        }
        strong = {
            "title": "Cloud computing breakthrough launches",
            "published_at": (now - timedelta(hours=2)).isoformat(),
        }

        self.assertEqual(calculate_importance_score(plain, now), 40)
        self.assertEqual(calculate_importance_score(strong, now), 90)

    def test_importance_score_does_not_reward_future_publication(self):
        now = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
        article = {
            "title": "Cloud computing update",
            "published_at": (now + timedelta(days=1)).isoformat(),
        }

        self.assertEqual(calculate_importance_score(article, now), 40)


if __name__ == "__main__":
    unittest.main()
