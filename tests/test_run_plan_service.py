import unittest

from backend.application.catalog_service import CatalogService
from backend.application.run_plan_service import RunPlanService
from models import Song, SongGroup, Step


class RunPlanServiceTests(unittest.TestCase):
    def make_catalog(self, steps):
        song = Song("Demo", "keyword", 10, buffer_seconds=2, step_preset="Flow")
        group = SongGroup("Queue", [song])
        return CatalogService(
            [group],
            [{"name": "Flow", "steps": steps}],
            active_song_group="Queue",
        )

    def test_reports_resolved_workflow_timing_and_missing_targets(self):
        catalog = self.make_catalog(
            [
                Step("known point", "click", target="Run"),
                Step("missing image", "image_click", value="Card", verify_target="Ready"),
                Step("duration", "wait", value="{total}"),
                Step("hold", "key_hold", value="space@0.5", wait_after="0.25"),
            ]
        )
        targets = {
            "active_point_group": "Default",
            "point_groups": [{"name": "Default", "points": [{"name": "Run", "x": 1, "y": 2}]}],
            "image_targets": [{"name": "Card", "template_path": "card.png"}],
        }
        validated = []
        service = RunPlanService(
            catalog,
            target_provider=lambda: targets,
            template_validator=lambda name: validated.append(name),
        )

        report = service.inspect("Queue")

        self.assertFalse(report["ready"])
        self.assertEqual(report["item_count"], 1)
        self.assertEqual(report["action_count"], 4)
        self.assertAlmostEqual(report["estimated_seconds"], 12.75)
        self.assertEqual(validated, ["Card"])
        issue = next(item for item in report["issues"] if item["code"] == "missing_verify_target")
        self.assertEqual(issue["item_name"], "Demo")
        self.assertEqual(issue["step_name"], "missing image")

    def test_workflow_resolution_failure_is_reported(self):
        catalog = self.make_catalog([Step("log", "log", value="ok")])
        catalog.prepare_job = lambda _job: (_ for _ in ()).throw(ValueError("preset missing"))

        report = RunPlanService(catalog).inspect("Queue")

        self.assertFalse(report["ready"])
        self.assertEqual(report["item_count"], 1)
        self.assertEqual(report["items"][0]["actions"], 0)
        self.assertEqual(report["issues"][0]["code"], "invalid_workflow")
    def test_invalid_variable_and_empty_queue_are_reported(self):
        catalog = self.make_catalog([Step("bad variable", "wait", value="{missing}")])
        service = RunPlanService(catalog)

        report = service.inspect("Queue")
        empty_catalog = CatalogService([SongGroup("Empty", [])], [], active_song_group="Empty")
        empty_report = RunPlanService(empty_catalog).inspect("Empty")

        self.assertFalse(report["ready"])
        self.assertTrue(any(issue["code"] == "invalid_variable" for issue in report["issues"]))
        self.assertFalse(empty_report["ready"])
        self.assertEqual(empty_report["issues"][0]["code"], "empty_queue")


if __name__ == "__main__":
    unittest.main()