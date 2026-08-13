import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import build_application
from backend.transport.http_api import SESSION_HEADER


class BackendCompositionTests(unittest.TestCase):
    TOKEN = "composition-test-token"

    def test_real_mode_runs_safe_actions_through_default_executor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "macro_config.json"
            playlist_path = root / "playlist.json"
            config_path.write_text(
                json.dumps(
                    {
                        "focus_window": False,
                        "input_mode": "foreground",
                        "steps": [
                            {
                                "name": "记录",
                                "kind": "log",
                                "value": "composition-ok",
                                "enabled": True,
                            },
                            {
                                "name": "零秒等待",
                                "kind": "wait",
                                "value": "0",
                                "enabled": True,
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            playlist_path.write_text(
                json.dumps(
                    [
                        {
                            "title": "安全测试",
                            "keyword": "safe",
                            "duration_seconds": 0,
                            "buffer_seconds": 0,
                            "enabled": True,
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            app = build_application(
                session_token=self.TOKEN,
                config_path=str(config_path),
                playlist_path=str(playlist_path),
            )
            headers = {SESSION_HEADER: self.TOKEN}
            with TestClient(app) as client:
                with client.websocket_connect(f"/api/events?token={self.TOKEN}") as websocket:
                    self.assertEqual(websocket.receive_json()["type"], "connection.ready")
                    response = client.post(
                        "/api/runner/start",
                        headers=headers,
                        json={"simulation": False},
                    )
                    self.assertEqual(response.status_code, 200)
                    events = []
                    log_messages = []
                    while "runner.completed" not in events:
                        event = websocket.receive_json()
                        events.append(event["type"])
                        if event["type"] == "log.appended":
                            log_messages.append(event["data"]["message"])
                app.state.runner.join(1)

        self.assertIn("composition-ok", log_messages)
        self.assertEqual(events.count("step.started"), 2)
        self.assertEqual(app.state.runner.status.value, "completed")
        self.assertEqual(app.state.runner.mode, "real")

    def test_saving_presets_synchronizes_active_legacy_steps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "macro_config.json"
            playlist_path = root / "playlist.json"
            config_path.write_text(
                json.dumps(
                    {
                        "active_step_preset": "视觉流程",
                        "steps": [{"name": "旧搜索", "kind": "click", "target": "搜索按钮"}],
                        "step_presets": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            playlist_path.write_text(
                json.dumps({"active_song_group": "默认", "song_groups": [{"name": "默认", "songs": []}]}),
                encoding="utf-8",
            )
            app = build_application(
                session_token=self.TOKEN,
                config_path=str(config_path),
                playlist_path=str(playlist_path),
            )
            payload = [
                {
                    "name": "视觉流程",
                    "steps": [
                        {
                            "name": "搜索",
                            "kind": "image_click",
                            "target": "",
                            "value": "搜索图标",
                            "enabled": True,
                            "wait_after": "",
                        }
                    ],
                }
            ]
            with TestClient(app) as client:
                response = client.put(
                    "/api/presets",
                    headers={SESSION_HEADER: self.TOKEN},
                    json=payload,
                )
                self.assertEqual(response.status_code, 200)
            saved = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(saved["active_step_preset"], "视觉流程")
        self.assertEqual(saved["steps"][0]["kind"], "image_click")
        self.assertEqual(saved["steps"][0]["value"], "搜索图标")


if __name__ == "__main__":
    unittest.main()
