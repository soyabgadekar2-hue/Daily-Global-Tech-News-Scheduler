import unittest
from datetime import date, datetime, timezone
from unittest.mock import Mock

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from briefing_service import generate_daily_briefing


def article(title, url, category, score, description="A short report."):
    return {
        "title": title,
        "url": url,
        "category": category,
        "importance_score": score,
        "description": description,
        "source": "Example News",
        "published_at": "2026-10-21T12:00:00Z",
    }


class BriefingServiceTests(unittest.TestCase):
    def setUp(self):
        self.news = Mock()
        self.briefings = Mock()
        self.briefings.find_one.return_value = None
        self.briefings.insert_one.return_value.inserted_id = ObjectId()

    def generate(self, articles, article_limit=15):
        self.news.find.return_value = articles
        return generate_daily_briefing(
            briefing_date=date(2026, 10, 21),
            article_limit=article_limit,
            news_collection=self.news,
            briefings_collection=self.briefings,
        )

    def test_selects_high_scoring_articles_and_returns_serializable_id(self):
        self.generate(
            [
                article("Lower scored AI report", "https://example.com/low", "AI", 20),
                article("Higher scored AI report", "https://example.com/high", "AI", 90),
            ],
            article_limit=1,
        )

        inserted = self.briefings.insert_one.call_args.args[0]
        selected = inserted["news"]["AI"][0]
        self.assertEqual(selected["title"], "Higher scored AI report")

        generated = generate_daily_briefing(
            briefing_date=date(2026, 10, 21),
            news_collection=self.news,
            briefings_collection=self.briefings,
        )
        self.assertIsInstance(generated["_id"], str)

    def test_selects_multiple_categories_before_repeating_one(self):
        self.generate(
            [
                article("AI best", "https://example.com/ai1", "AI", 100),
                article("AI next", "https://example.com/ai2", "AI", 90),
                article("Cloud best", "https://example.com/cloud1", "Cloud", 80),
            ],
            article_limit=2,
        )

        grouped_news = self.briefings.insert_one.call_args.args[0]["news"]
        self.assertEqual(list(grouped_news), ["AI", "Cloud"])
        self.assertEqual([len(entries) for entries in grouped_news.values()], [1, 1])

    def test_summary_uses_description_and_marks_missing_description_limited(self):
        self.generate(
            [
                article(
                    "Described story",
                    "https://example.com/1",
                    "AI",
                    90,
                    "First sentence. Later details are not needed.",
                ),
                article(
                    "Limited story",
                    "https://example.com/2",
                    "Cloud",
                    80,
                    "",
                ),
            ]
        )

        news = self.briefings.insert_one.call_args.args[0]["news"]
        self.assertEqual(news["AI"][0]["summary"], "First sentence.")
        self.assertIn("description is limited", news["Cloud"][0]["summary"])
        self.assertIn("Generated suggestion", news["AI"][0]["why_it_matters"])

    def test_empty_news_creates_empty_briefing_without_fabricated_stories(self):
        generated = self.generate([])

        inserted = self.briefings.insert_one.call_args.args[0]
        self.assertEqual(inserted["news"], {})
        self.assertIn("No articles are available", inserted["learning_of_the_day"]["text"])
        self.assertEqual(generated["briefing_date"], "2026-10-21")

    def test_existing_briefing_is_preserved_on_rerun(self):
        existing = {
            "_id": ObjectId(),
            "briefing_date": "2026-10-21",
            "news": {"Existing": []},
            "created_at": datetime(2026, 10, 21, tzinfo=timezone.utc),
        }
        self.briefings.find_one.return_value = existing

        generated = generate_daily_briefing(
            briefing_date=date(2026, 10, 21),
            news_collection=self.news,
            briefings_collection=self.briefings,
        )

        self.assertEqual(generated["news"], {"Existing": []})
        self.assertIsInstance(generated["_id"], str)
        self.news.find.assert_not_called()
        self.briefings.insert_one.assert_not_called()

    def test_duplicate_date_race_returns_existing_briefing(self):
        existing = {"briefing_date": "2026-10-21", "news": {}}
        self.briefings.insert_one.side_effect = DuplicateKeyError("duplicate date")
        self.briefings.find_one.side_effect = [None, existing]

        generated = self.generate([])

        self.assertEqual(generated["briefing_date"], "2026-10-21")
        self.assertEqual(self.briefings.find_one.call_count, 2)


if __name__ == "__main__":
    unittest.main()
