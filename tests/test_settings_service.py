import json
import tempfile
import unittest
from pathlib import Path

from backend.application.settings_service import SettingsService
from backend.infrastructure.config_repository import ConfigRepository


class SettingsServiceTests(unittest.TestCase):
    def test_reads_and_updates_only_target_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "macro_config.json"
            path.write_text(json.dumps({"steps": [{"name": "keep"}], "window_hint": "旧窗口"}), encoding="utf-8")
            service = SettingsService(ConfigRepository(str(path)))
            saved = service.replace({
                "window_hint": "逆水寒手游桌面版",
                "focus_window": False,
                "input_mode": "window_message",
                "confirm_step_test": False,
                "preview_clicks": True,
            })
            document = ConfigRepository(str(path)).load()
        self.assertEqual(saved["window_hint"], "逆水寒手游桌面版")
        self.assertEqual(saved["input_mode"], "window_message")
        self.assertFalse(saved["focus_window"])
        self.assertFalse(saved["confirm_step_test"])
        self.assertTrue(saved["preview_clicks"])
        self.assertTrue(document["preview_clicks"])
        self.assertEqual(document["steps"], [{"name": "keep"}])

    def test_rejects_empty_window_hint(self):
        with tempfile.TemporaryDirectory() as directory:
            service = SettingsService(ConfigRepository(str(Path(directory) / "macro_config.json")))
            with self.assertRaisesRegex(ValueError, "不能为空"):
                service.replace({"window_hint": "", "focus_window": True, "input_mode": "foreground"})


if __name__ == "__main__":
    unittest.main()
