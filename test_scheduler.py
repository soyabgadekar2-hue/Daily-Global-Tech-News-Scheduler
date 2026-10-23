import unittest
from datetime import date
from unittest.mock import Mock, patch

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.blocking import BlockingScheduler

import scheduler


class SchedulerTests(unittest.TestCase):
    def test_workflow_calls_services_in_order(self):
        calls = []
        articles = [{"title": "Example", "url": "https://example.com"}]
        fetcher = Mock(side_effect=lambda: calls.append("fetch") or articles)
        saver = Mock(side_effect=lambda received: calls.append("save") or {
            "inserted": len(received),
            "duplicates": 0,
            "rejected": 0,
        })
        briefing = Mock(
            side_effect=lambda briefing_date: calls.append("briefing")
            or {"briefing_date": briefing_date.isoformat()}
        )

        with self.assertLogs("scheduler", level="INFO"):
            succeeded = scheduler.run_daily_workflow(
                fetcher=fetcher,
                saver=saver,
                briefing_generator=briefing,
            )

        self.assertTrue(succeeded)
        self.assertEqual(calls, ["fetch", "save", "briefing"])
        saver.assert_called_once_with(articles)
        self.assertEqual(briefing.call_count, 1)
        self.assertIsInstance(briefing.call_args.args[0], date)

    def test_fetch_failure_stops_later_steps_and_logs_safely(self):
        fetcher = Mock(side_effect=scheduler.NewsServiceError("safe test failure"))
        saver = Mock()
        briefing = Mock()

        with self.assertLogs("scheduler", level="ERROR") as captured:
            succeeded = scheduler.run_daily_workflow(
                fetcher=fetcher,
                saver=saver,
                briefing_generator=briefing,
            )

        self.assertFalse(succeeded)
        self.assertIn("News fetch failed", captured.output[0])
        saver.assert_not_called()
        briefing.assert_not_called()

    def test_storage_failure_stops_briefing_and_logs_safely(self):
        saver = Mock(side_effect=ConnectionError("private connection details"))

        with self.assertLogs("scheduler", level="ERROR") as captured:
            succeeded = scheduler.run_daily_workflow(
                fetcher=Mock(return_value=[]),
                saver=saver,
                briefing_generator=Mock(),
            )

        self.assertFalse(succeeded)
        self.assertIn("Saving news failed", captured.output[0])
        self.assertNotIn("private connection details", captured.output[0])

    def test_briefing_failure_returns_failure_and_logs(self):
        briefing = Mock(side_effect=RuntimeError("private database details"))

        with self.assertLogs("scheduler", level="ERROR") as captured:
            succeeded = scheduler.run_daily_workflow(
                fetcher=Mock(return_value=[]),
                saver=Mock(return_value={}),
                briefing_generator=briefing,
            )

        self.assertFalse(succeeded)
        self.assertIn("Daily briefing generation failed", captured.output[0])
        self.assertNotIn("private database details", captured.output[0])

    def test_test_mode_uses_safe_stand_ins(self):
        with (
            patch("scheduler.fetch_technology_news", side_effect=AssertionError),
            patch("scheduler.save_articles", side_effect=AssertionError),
            patch("scheduler.generate_daily_briefing", side_effect=AssertionError),
            self.assertLogs("scheduler", level="INFO") as captured,
        ):
            self.assertTrue(scheduler.run_test_mode())

        self.assertTrue(
            any("No network request or database write was made" in line
                for line in captured.output)
        )

    def test_creates_daily_job_with_timezone_and_overlap_policy(self):
        with (
            patch.object(scheduler.config, "NEWS_SCHEDULE_HOUR", 6),
            patch.object(scheduler.config, "NEWS_SCHEDULE_MINUTE", 15),
            patch.object(scheduler.config, "NEWS_SCHEDULE_TIMEZONE", "Asia/Kolkata"),
        ):
            instance = scheduler.create_scheduler()

        self.assertIsInstance(instance, BlockingScheduler)
        [job] = instance.get_jobs()
        self.assertEqual(job.id, "daily_tech_news_workflow")
        self.assertEqual(job.max_instances, 1)
        self.assertTrue(job.coalesce)
        self.assertEqual(job.misfire_grace_time, 3600)
        self.assertEqual(job.trigger.timezone.key, "Asia/Kolkata")
        fields = {field.name: str(field) for field in job.trigger.fields}
        self.assertEqual(fields["hour"], "6")
        self.assertEqual(fields["minute"], "15")

    def test_creates_async_api_job_with_same_schedule_settings(self):
        with (
            patch.object(scheduler.config, "NEWS_SCHEDULE_HOUR", 7),
            patch.object(scheduler.config, "NEWS_SCHEDULE_MINUTE", 30),
            patch.object(scheduler.config, "NEWS_SCHEDULE_TIMEZONE", "Asia/Kolkata"),
        ):
            instance = scheduler.create_api_scheduler()

        self.assertIsInstance(instance, AsyncIOScheduler)
        [job] = instance.get_jobs()
        self.assertEqual(job.id, "daily_tech_news_workflow")
        self.assertEqual(job.max_instances, 1)
        self.assertTrue(job.coalesce)
        self.assertEqual(job.misfire_grace_time, 3600)
        self.assertEqual(job.trigger.timezone.key, "Asia/Kolkata")

    def test_scheduled_workflow_logs_unexpected_errors_without_details(self):
        with (
            patch(
                "scheduler.run_daily_workflow",
                side_effect=RuntimeError("private connection details"),
            ),
            self.assertLogs("scheduler", level="ERROR") as captured,
        ):
            scheduler.run_scheduled_workflow()

        self.assertIn("failed unexpectedly (RuntimeError)", captured.output[0])
        self.assertNotIn("private connection details", captured.output[0])

    def test_rejects_invalid_schedule_time(self):
        with patch.object(scheduler.config, "NEWS_SCHEDULE_HOUR", 24):
            with self.assertRaisesRegex(ValueError, "between 0 and 23"):
                scheduler.create_scheduler()

    def test_rejects_unknown_timezone(self):
        with (
            patch.object(scheduler.config, "NEWS_SCHEDULE_HOUR", 6),
            patch.object(scheduler.config, "NEWS_SCHEDULE_MINUTE", 0),
            patch.object(scheduler.config, "NEWS_SCHEDULE_TIMEZONE", "Mars/Olympus"),
        ):
            with self.assertRaisesRegex(ValueError, "valid IANA time-zone"):
                scheduler.create_scheduler()


if __name__ == "__main__":
    unittest.main()
