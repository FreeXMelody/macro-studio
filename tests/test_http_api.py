import unittest

from fastapi.testclient import TestClient

from backend.application.catalog_service import CatalogService
from backend.application.event_bus import EventBus
from backend.application.runner_service import RunnerService
from backend.transport.http_api import SESSION_HEADER, create_app
from models import Song, SongGroup, Step



class FakeExecutor:
    def __init__(self):
        self.prepared = []
        self.executed = []
        self.cleanup_calls = 0

    def prepare_job(self, job, prepared):
        self.prepared.append(job.song.title)
        return prepared

    def execute_step(self, step, _job, _prepared):
        self.executed.append(step.name)

    def cleanup(self):
        self.cleanup_calls += 1
class LocalApiTests(unittest.TestCase):
    TOKEN = "test-session-token"

    def make_stack(self, save_playlists=None, save_presets=None, step_seconds=0.001, executor=None, settings=None, window_inspector=None, point_preview=None):
        song = Song(
            title="问爱",
            keyword="问爱",
            duration_seconds=30,
            buffer_seconds=5,
            step_preset="播放流程",
        )
        group = SongGroup(name="古风", songs=[song], step_preset="")
        presets = [
            {
                "name": "播放流程",
                "steps": [
                    Step(name="输入搜索词", kind="paste", value="{keyword}"),
                    Step(name="等待结果", kind="wait", value="1"),
                ],
            }
        ]
        catalog = CatalogService(
            [group],
            presets,
            active_song_group="古风",
            save_playlists=save_playlists,
            save_presets=save_presets,
        )
        event_bus = EventBus()
        runner = RunnerService(
            catalog,
            event_bus,
            simulation_step_seconds=step_seconds,
            executor=executor,
        )
        app = create_app(
            catalog,
            self.TOKEN,
            event_bus=event_bus,
            runner=runner,
            settings=settings,
            window_inspector=window_inspector,
            point_preview=point_preview,
        )
        return app, catalog, runner

    @property
    def headers(self):
        return {SESSION_HEADER: self.TOKEN}

    def test_simulation_applies_fractional_wait_after(self):
        _app, catalog, runner = self.make_stack(step_seconds=0.1)
        job = catalog.jobs()[0]
        prepared = catalog.prepare_job(job)
        waits = []
        runner.control.wait = lambda seconds, poll_interval=0.2: waits.append(seconds) or True

        runner._execute_simulated_step(
            Step(name="模拟动作", kind="log", value="", wait_after="0.5"),
            job,
            prepared,
        )

        self.assertEqual(len(waits), 1)
        self.assertAlmostEqual(waits[0], 0.6)

    def test_health_and_catalog_require_session_token(self):
        app, _catalog, _runner = self.make_stack()
        with TestClient(app) as client:
            self.assertEqual(client.get("/api/health").status_code, 401)
            health = client.get("/api/health", headers=self.headers)
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json()["status"], "ok")
            playlists = client.get("/api/playlists", headers=self.headers)
            self.assertEqual(playlists.json()["song_groups"][0]["songs"][0]["title"], "问爱")

    def test_playlist_and_preset_updates_use_catalog_callbacks(self):
        saved_playlists = []
        saved_presets = []
        app, catalog, _runner = self.make_stack(saved_playlists.append, saved_presets.append)
        playlist_payload = {
            "active_song_group": "流行",
            "song_groups": [
                {
                    "name": "流行",
                    "step_preset": "",
                    "songs": [
                        {
                            "title": "下一首",
                            "keyword": "下一首",
                            "duration_seconds": 20,
                            "buffer_seconds": 4,
                            "enabled": True,
                            "step_preset": "",
                        }
                    ],
                }
            ],
        }
        preset_payload = [
            {
                "name": "新流程",
                "steps": [
                    {
                        "name": "记录",
                        "kind": "log",
                        "target": "",
                        "value": "开始",
                        "enabled": True,
                        "wait_after": "",
                    }
                ],
            }
        ]
        with TestClient(app) as client:
            playlist_response = client.put("/api/playlists", headers=self.headers, json=playlist_payload)
            self.assertEqual(playlist_response.status_code, 200)
            preset_response = client.put("/api/presets", headers=self.headers, json=preset_payload)
            self.assertEqual(preset_response.status_code, 200)
        self.assertEqual(saved_playlists[0]["active_song_group"], "流行")
        self.assertEqual(saved_presets[0][0]["name"], "新流程")
        self.assertEqual(catalog.presets_document()[0]["steps"][0]["kind"], "log")

    def test_image_click_preset_round_trip_preserves_kind_and_target(self):
        app, catalog, _runner = self.make_stack()
        payload = [
            {
                "name": "视觉流程",
                "steps": [
                    {
                        "name": "识别搜索按钮",
                        "kind": "image_click",
                        "target": "",
                        "value": "搜索按钮图像",
                        "enabled": True,
                        "wait_after": "0.5",
                    }
                ],
            }
        ]
        with TestClient(app) as client:
            response = client.put("/api/presets", headers=self.headers, json=payload)
            loaded = client.get("/api/presets", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        step = loaded.json()[0]["steps"][0]
        self.assertEqual(step["kind"], "image_click")
        self.assertEqual(step["value"], "搜索按钮图像")
        self.assertEqual(catalog.presets_document()[0]["steps"][0]["kind"], "image_click")
    def test_playlist_update_rejects_invalid_group_names(self):
        app, _catalog, _runner = self.make_stack()
        base_group = {"name": "古风", "step_preset": "", "songs": []}
        invalid_documents = [
            ({"active_song_group": "", "song_groups": []}, "至少需要保留一个歌曲组"),
            (
                {"active_song_group": "古风", "song_groups": [base_group, dict(base_group)]},
                "歌曲组名称重复：古风",
            ),
            (
                {"active_song_group": "全部", "song_groups": [{**base_group, "name": "全部"}]},
                "“全部”是系统保留名称",
            ),
        ]
        with TestClient(app) as client:
            for payload, expected_detail in invalid_documents:
                response = client.put("/api/playlists", headers=self.headers, json=payload)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["detail"], expected_detail)

    def test_point_preview_endpoint_forwards_name_and_coordinates(self):
        calls = []

        class Preview:
            def preview(self, name, x, y, duration):
                calls.append((name, x, y, duration))
                return {"status": "showing", "name": name, "x": x, "y": y, "duration": duration}

        app, _catalog, _runner = self.make_stack(point_preview=Preview())
        with TestClient(app) as client:
            response = client.post(
                "/api/targets/point-preview",
                headers=self.headers,
                json={"name": "播放", "x": 1280, "y": 720, "duration": 2.2},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "showing")
        self.assertEqual(calls, [("播放", 1280, 720, 2.2)])
    def test_websocket_observes_complete_simulated_song_run(self):
        app, _catalog, runner = self.make_stack()
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/events?token={self.TOKEN}") as websocket:
                ready = websocket.receive_json()
                self.assertEqual(ready["type"], "connection.ready")
                response = client.post(
                    "/api/runner/start",
                    headers=self.headers,
                    json={"active_group": "古风", "simulation": True},
                )
                self.assertEqual(response.status_code, 200)
                events = []
                while "runner.completed" not in events:
                    event = websocket.receive_json()
                    events.append(event["type"])
                runner.join(1)
        self.assertIn("runner.started", events)
        self.assertEqual(events.count("step.started"), 2)
        self.assertIn("song.started", events)
        self.assertEqual(runner.status.value, "completed")

    def test_single_step_real_execution_uses_executor(self):
        executor = FakeExecutor()
        app, _catalog, runner = self.make_stack(executor=executor)
        payload = {
            "step": {
                "name": "单步记录",
                "kind": "log",
                "target": "",
                "value": "ok",
                "enabled": True,
                "wait_after": "",
            },
            "song": {
                "title": "问爱",
                "keyword": "问爱",
                "duration_seconds": 30,
                "buffer_seconds": 5,
                "enabled": True,
                "step_preset": "",
            },
        }
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/events?token={self.TOKEN}") as websocket:
                websocket.receive_json()
                response = client.post("/api/runner/test-step", headers=self.headers, json=payload)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["mode"], "real")
                messages = []
                while not any("单步测试成功" in message for message in messages):
                    event = websocket.receive_json()
                    if event["type"] == "log.appended":
                        messages.append(str(event["data"].get("message", "")))
                runner.join(1)
        self.assertTrue(any("单步测试开始" in message for message in messages))
        self.assertTrue(any("单步测试成功" in message for message in messages))
        self.assertEqual(executor.executed, ["单步记录"])
        self.assertEqual(executor.cleanup_calls, 1)
        self.assertEqual(runner.status.value, "completed")
    def test_real_execution_requires_an_executor(self):
        app, _catalog, _runner = self.make_stack()
        with TestClient(app) as client:
            response = client.post(
                "/api/runner/start",
                headers=self.headers,
                json={"simulation": False},
            )
        self.assertEqual(response.status_code, 503)

    def test_real_execution_uses_executor_and_reports_mode(self):
        executor = FakeExecutor()
        app, _catalog, runner = self.make_stack(executor=executor)
        with TestClient(app) as client:
            response = client.post(
                "/api/runner/start",
                headers=self.headers,
                json={"active_group": "古风", "simulation": False},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["mode"], "real")
            runner.join(1)
            state = client.get("/api/runner", headers=self.headers).json()
        self.assertEqual(state["mode"], "real")
        self.assertEqual(executor.prepared, ["问爱"])
        self.assertEqual(executor.executed, ["输入搜索词", "等待结果"])
        self.assertEqual(executor.cleanup_calls, 1)
        self.assertEqual(runner.status.value, "completed")


if __name__ == "__main__":
    unittest.main()
