import unittest
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo.errors import PyMongoError

import api


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.database = MagicMock()
        self.news = MagicMock()
        self.briefings = MagicMock()
        self.database.__getitem__.side_effect = {
            "news": self.news,
            "daily_briefings": self.briefings,
        }.__getitem__
        self.news.find_one.return_value = None
        self.briefings.find_one.return_value = None
        self.client = TestClient(api.app)
        self.connection = patch("api.connect_to_mongodb", return_value=self.database)
        self.connection.start()
        self.addCleanup(self.connection.stop)
        self._configure_cursor(self.news)
        self._configure_cursor(self.briefings)

    @staticmethod
    def _configure_cursor(collection):
        cursor = MagicMock()
        collection.find.return_value = cursor
        cursor.sort.return_value = cursor
        cursor.skip.return_value = cursor
        cursor.limit.return_value = []
        collection.count_documents.return_value = 0

    def test_health_reports_safe_connected_status(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "connected"})
        self.database.__getitem__.assert_called_with("news")

    def test_news_list_returns_paginated_json(self):
        article_id = ObjectId()
        self.news.find.return_value.sort.return_value.skip.return_value.limit.return_value = [
            {
                "_id": article_id,
                "title": "Cloud update",
                "fetched_at": datetime(2026, 10, 22, tzinfo=timezone.utc),
            }
        ]
        self.news.count_documents.return_value = 1

        response = self.client.get("/news?skip=2&limit=5")

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual((result["skip"], result["limit"], result["total"]), (2, 5, 1))
        self.assertEqual(result["items"][0]["_id"], str(article_id))
        self.assertEqual(
            result["items"][0]["fetched_at"],
            "2026-10-22T00:00:00+00:00",
        )

    def test_news_category_and_search_use_existing_fields(self):
        self.client.get("/news/category/Cloud%20Computing")
        self.news.find.assert_called_with({"category": "Cloud Computing"})

        self.client.get("/news/search?keyword=python")
        query = self.news.find.call_args.args[0]
        self.assertEqual(query["$or"][0]["title"]["$regex"], "python")
        self.assertEqual(query["$or"][1]["description"]["$options"], "i")

    def test_search_escapes_regular_expression_input(self):
        self.client.get("/news/search?keyword=%5Bpython%5D")

        query = self.news.find.call_args.args[0]
        self.assertEqual(query["$or"][0]["title"]["$regex"], r"\[python\]")

    def test_get_article_validates_id_and_returns_404_when_missing(self):
        invalid = self.client.get("/news/not-an-object-id")
        missing = self.client.get(f"/news/{ObjectId()}")

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(missing.status_code, 404)

    def test_get_article_returns_serializable_record(self):
        article_id = ObjectId()
        self.news.find_one.return_value = {
            "_id": article_id,
            "published_at": date(2026, 10, 22),
        }

        response = self.client.get(f"/news/{article_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["_id"], str(article_id))
        self.assertEqual(response.json()["published_at"], "2026-10-22")

    def test_briefing_list_and_date_lookup(self):
        self.briefings.find.return_value.sort.return_value.skip.return_value.limit.return_value = [
            {"briefing_date": "2026-10-22"}
        ]
        self.briefings.count_documents.return_value = 1
        listed = self.client.get("/briefings?limit=3")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["items"][0]["briefing_date"], "2026-10-22")

        self.briefings.find_one.return_value = {
            "_id": ObjectId(),
            "briefing_date": "2026-10-22",
            "created_at": datetime(2026, 10, 22, tzinfo=timezone.utc),
        }
        retrieved = self.client.get("/briefings/2026-10-22")
        self.assertEqual(retrieved.status_code, 200)
        self.assertEqual(
            retrieved.json()["created_at"],
            "2026-10-22T00:00:00+00:00",
        )
        self.briefings.find_one.assert_called_with({"briefing_date": "2026-10-22"})

    def test_invalid_date_and_missing_briefing(self):
        self.assertEqual(self.client.get("/briefings/2026-2-3").status_code, 400)
        self.briefings.find_one.return_value = None
        self.assertEqual(self.client.get("/briefings/2026-10-22").status_code, 404)

    def test_pagination_and_search_validation(self):
        self.assertEqual(self.client.get("/news?skip=-1").status_code, 422)
        self.assertEqual(self.client.get("/news?limit=101").status_code, 422)
        self.assertEqual(self.client.get("/news/search?keyword=%20%20").status_code, 422)

    def test_database_errors_are_returned_without_sensitive_details(self):
        self.connection.stop()
        self.connection = patch(
            "api.connect_to_mongodb",
            side_effect=PyMongoError("mongodb://user:secret@private-host"),
        )
        self.connection.start()

        with self.assertLogs("api", level="ERROR"):
            response = self.client.get("/news")

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret", response.text)
        self.assertNotIn("private-host", response.text)

    def test_lifespan_prepares_database_and_starts_then_stops_scheduler(self):
        startup_calls = []
        scheduler = MagicMock()
        scheduler.running = True
        scheduler.start.side_effect = lambda: startup_calls.append("start")

        with (
            patch(
                "api.prepare_collections",
                side_effect=lambda: startup_calls.append("prepare"),
            ) as prepare,
            patch("api.create_api_scheduler", return_value=scheduler) as create,
            TestClient(api.app) as client,
        ):
            prepare.assert_called_once_with()
            create.assert_called_once_with()
            scheduler.start.assert_called_once_with()
            self.assertEqual(startup_calls, ["prepare", "start"])
            scheduler.shutdown.assert_not_called()
            self.assertEqual(client.get("/health").status_code, 200)

        scheduler.shutdown.assert_called_once_with(wait=False)
        self.assertIsNone(getattr(api.app.state, "scheduler", None))
        self.assertFalse(api.app.state.scheduler_starting)

    def test_lifespan_rejects_duplicate_scheduler_start(self):
        scheduler = MagicMock()
        scheduler.running = True

        with (
            patch("api.prepare_collections"),
            patch("api.create_api_scheduler", return_value=scheduler) as create,
            TestClient(api.app),
        ):
            with self.assertRaises(RuntimeError):
                with TestClient(api.app):
                    pass

        create.assert_called_once_with()
        scheduler.start.assert_called_once_with()
        scheduler.shutdown.assert_called_once_with(wait=False)

    def test_lifespan_cleans_up_scheduler_when_startup_fails(self):
        scheduler = MagicMock()
        scheduler.running = True
        scheduler.start.side_effect = RuntimeError("private startup details")

        with (
            patch("api.prepare_collections"),
            patch("api.create_api_scheduler", return_value=scheduler),
            self.assertLogs("api", level="ERROR") as captured,
        ):
            with self.assertRaisesRegex(RuntimeError, "private startup details"):
                with TestClient(api.app):
                    pass

        scheduler.shutdown.assert_called_once_with(wait=False)
        self.assertIsNone(getattr(api.app.state, "scheduler", None))
        self.assertFalse(api.app.state.scheduler_starting)
        self.assertNotIn("private startup details", captured.output[0])


if __name__ == "__main__":
    unittest.main()
