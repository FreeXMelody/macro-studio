import json
import os
import tempfile
import time
import unittest

from backend.application.stage_service import StageService
from stage_api import DEFAULT_STAGE_API_CONFIG, StageWork
from stage_diagnostics import DiagnosticReport


class MemoryRepository:
    def __init__(self, document=None):
        self.value = dict(document or {})

    def load(self):
        return dict(self.value)

    def mutate(self, mutator):
        mutator(self.value)
        return dict(self.value)


class StageServiceTests(unittest.TestCase):
    def make_config(self):
        return {
            **DEFAULT_STAGE_API_CONFIG,
            "role_id": "123",
            "user_id": "456",
            "skey": "secret",
            "sort": "hot",
            "page_size": "18",
        }

    def test_search_persists_config_enriches_duration_and_caches_cover(self):
        repository = MemoryRepository()
        calls = []

        def searcher(keyword, config, page):
            calls.append((keyword, config["role_id"], page))
            return [
                StageWork(
                    work_id=7,
                    name="问爱",
                    summary="测试简介",
                    designer_name="期迷",
                    hot=99,
                    like_count=8,
                    collect_count=12,
                    property_url="https://property",
                    cover_url="https://cdn.example/cover.png",
                    work_type=1,
                    sub_type=1,
                    actor_count=1,
                )
            ]

        def load_duration(work):
            work.duration_seconds = 30
            return work

        service = StageService(
            repository,
            searcher=searcher,
            duration_loader=load_duration,
            byte_fetcher=lambda _url, _config: b"png",
        )
        result = service.search("问爱", self.make_config())

        self.assertEqual(calls, [("问爱", "123", 1)])
        self.assertEqual(result["works"][0]["duration_seconds"], 30)
        self.assertEqual(result["works"][0]["category_label"], "单人")
        self.assertEqual(repository.value["stage_search_keyword"], "问爱")
        self.assertEqual(service.cover(7), (b"png", "image/png"))

    def test_rejects_an_untrusted_search_endpoint(self):
        service = StageService(MemoryRepository())
        config = self.make_config()
        config["base_url"] = "https://example.com/proxy"

        with self.assertRaisesRegex(ValueError, "不受信任"):
            service.search("问爱", config)

    def test_diagnostics_run_in_background_and_publish_a_structured_summary(self):
        report = DiagnosticReport("cache", "game")
        report.cache_files_seen = 14
        report.method_candidates = ["openWork", "playAction"]
        report.action_play_logs = ["play"]
        report.notes = ["发现桥接候选"]

        service = StageService(
            MemoryRepository(),
            diagnostic_runner=lambda: report,
        )
        state = service.start_diagnostics()
        self.assertIn(state["status"], {"running", "completed"})

        deadline = time.monotonic() + 2
        while service.diagnostics_state()["status"] == "running" and time.monotonic() < deadline:
            time.sleep(0.02)

        state = service.diagnostics_state()
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["summary"]["cache_files_seen"], 14)
        self.assertEqual(state["summary"]["method_candidates"], 2)
        self.assertEqual(state["notes"], ["发现桥接候选"])
        self.assertIn("Macro Studio 剧组诊断报告", state["report"])

    def test_capture_validates_and_saves_the_captured_request(self):
        repository = MemoryRepository()
        config = self.make_config()

        def launcher(path, timeout):
            self.assertEqual(timeout, 15)
            with open(path, "w", encoding="utf-8") as stream:
                json.dump({"ok": True, "config": {**config, "keyword": "问爱"}}, stream)

        service = StageService(
            repository,
            capture_launcher=launcher,
            searcher=lambda _keyword, _config, page: [],
        )
        state = service.start_capture(15)
        self.assertEqual(state["status"], "listening")

        deadline = time.monotonic() + 2
        while service.capture_state()["status"] in {"listening", "validating"} and time.monotonic() < deadline:
            time.sleep(0.05)

        state = service.capture_state()
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["keyword"], "问爱")
        self.assertEqual(repository.value["stage_api"]["role_id"], "123")


if __name__ == "__main__":
    unittest.main()