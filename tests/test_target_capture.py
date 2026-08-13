import os
import tempfile
import unittest

from PIL import Image

from backend.infrastructure.point_capture import PointCaptureMonitor
from backend.infrastructure.point_preview import PointPreviewService
from backend.infrastructure.region_selector import RegionSelector
from backend.infrastructure.target_window import TargetWindowInspector
from backend.infrastructure.vision_test_service import VisionTestService
from vision import MatchFailure, MatchResult, _match_template_image


class PointCaptureMonitorTests(unittest.TestCase):
    def test_f8_only_captures_when_armed(self):
        pressed = [True, True]
        monitor = PointCaptureMonitor(
            is_pressed=lambda: pressed.pop(0),
            get_position=lambda: (321, 654),
        )

        self.assertFalse(monitor.poll_once())
        monitor.arm("逆水寒", "搜索框")
        self.assertTrue(monitor.poll_once())
        self.assertEqual(
            monitor.state(),
            {
                "status": "captured",
                "group_name": "逆水寒",
                "point_name": "搜索框",
                "x": 321,
                "y": 654,
            },
        )

    def test_cancel_resets_capture(self):
        monitor = PointCaptureMonitor(is_pressed=lambda: False)
        monitor.arm("默认", "按钮")

        state = monitor.cancel()

        self.assertEqual(state["status"], "idle")
        self.assertEqual(state["point_name"], "")


class PointPreviewServiceTests(unittest.TestCase):
    def test_preview_validates_and_forwards_point_details(self):
        rendered = []
        service = PointPreviewService(renderer=lambda *args: rendered.append(args))

        result = service.preview("搜索按钮", 420, 260, 1.5)
        service.join(1)

        self.assertEqual(result, {
            "status": "showing",
            "name": "搜索按钮",
            "x": 420,
            "y": 260,
            "duration": 1.5,
        })
        self.assertEqual(rendered, [("搜索按钮", 420, 260, 1.5)])

    def test_preview_rejects_invalid_input(self):
        service = PointPreviewService(renderer=lambda *_args: None)
        with self.assertRaisesRegex(ValueError, "名称不能为空"):
            service.preview("", 1, 2)
        with self.assertRaisesRegex(ValueError, "0.5 到 10"):
            service.preview("按钮", 1, 2, 0.1)


class TargetWindowInspectorTests(unittest.TestCase):
    def test_preflight_blocks_lower_integrity_input(self):
        inspector = TargetWindowInspector(
            config_provider=lambda: {
                "window_hint": "逆水寒",
                "input_mode": "window_message",
                "active_point_group": "游戏",
                "point_groups": [{"name": "游戏", "points": []}],
                "image_targets": [],
            }
        )
        inspector.probe = lambda *_args, **_kwargs: {
            "found": True,
            "title": "逆水寒手游桌面版",
            "process_elevated": True,
            "app_elevated": False,
            "input_allowed": False,
        }

        report = inspector.preflight()
        permission = next(item for item in report["checks"] if item["key"] == "input_permission")

        self.assertFalse(report["ready"])
        self.assertFalse(permission["ok"])
        self.assertIn("管理员身份重启 Macro Studio", permission["detail"])


class VisionTestServiceTests(unittest.TestCase):
    def test_uses_background_capture_when_target_window_exists(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "target.png")
            Image.new("RGB", (12, 10), "white").save(path)
            tester = VisionTestService(
                config_provider=lambda: {"window_hint": "逆水寒"},
                base_dir=directory,
                find_target_window=lambda hint: {"hwnd": 99, "title": hint},
                locate_window=lambda path, hwnd, region, threshold, *options: calls.append((path, hwnd, region, threshold, *options))
                or MatchResult(x=10, y=20, score=0.93, width=12, height=10),
            )

            result = tester.test({"template_path": "target.png", "region": "1,2,30,40", "threshold": 0.7})

        self.assertEqual(result["source"], "background")
        self.assertEqual(result["score"], 0.93)
        self.assertEqual(calls[0][1:], (99, "1,2,30,40", 0.7, "grayscale", "", 60, 160))

    def test_uses_screen_capture_without_window_hint(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "target.png")
            Image.new("RGB", (8, 8), "black").save(path)
            tester = VisionTestService(
                config_provider=lambda: {},
                base_dir=directory,
                locate_screen=lambda *_args: MatchResult(x=4, y=5, score=1.0, width=8, height=8),
            )

            result = tester.test({"template_path": path, "threshold": 0.8})

        self.assertEqual(result["source"], "screen")
        self.assertEqual((result["x"], result["y"]), (4, 5))

    def test_reports_a_normal_no_match_without_raising(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "target.png")
            Image.new("RGB", (8, 8), "black").save(path)
            tester = VisionTestService(
                config_provider=lambda: {},
                base_dir=directory,
                locate_screen=lambda *_args: (_ for _ in ()).throw(RuntimeError("未达到识别阈值")),
            )

            result = tester.test({"template_path": path, "threshold": 0.8})

        self.assertFalse(result["matched"])
        self.assertEqual(result["source"], "screen")
        self.assertIn("识别阈值", result["error"])


class VisionMatchingTests(unittest.TestCase):
    def test_masked_matching_ignores_changed_background(self):
        import cv2
        import numpy as np

        template = np.zeros((24, 24, 3), dtype=np.uint8)
        template[:, :] = (220, 30, 30)
        template[7:17, 8:16] = (255, 255, 255)
        screen = np.zeros((60, 70, 3), dtype=np.uint8)
        screen[:, :] = (30, 180, 60)
        screen[20:44, 28:52] = template
        screen[20:44, 28:52] = (20, 80, 220)
        screen[27:37, 36:44] = (255, 255, 255)
        mask = Image.new("L", (24, 24), 0)
        mask.paste(255, (8, 7, 16, 17))

        with tempfile.TemporaryDirectory() as directory:
            template_path = os.path.join(directory, "template.png")
            mask_path = os.path.join(directory, "mask.png")
            Image.fromarray(template).save(template_path)
            mask.save(mask_path)
            result = _match_template_image(
                cv2,
                np,
                Image,
                screen,
                template_path,
                0.9,
                "masked",
                mask_path,
                60,
                160,
                "",
            )

        self.assertGreaterEqual(result.score, 0.99)
        self.assertEqual((result.x, result.y), (40, 32))
        self.assertEqual(result.match_mode, "masked")

    def test_masked_edge_matching_ignores_edges_outside_template_contours(self):
        import cv2
        import numpy as np

        template = np.full((30, 30, 3), 30, dtype=np.uint8)
        template[8:22, 10:20] = 245
        screen = np.full((70, 80, 3), 15, dtype=np.uint8)
        for y in range(70):
            for x in range(80):
                screen[y, x] = 25 if (x // 3 + y // 3) % 2 else 105
        screen[28:42, 43:53] = 245
        mask = Image.new("L", (30, 30), 255)

        with tempfile.TemporaryDirectory() as directory:
            template_path = os.path.join(directory, "template.png")
            mask_path = os.path.join(directory, "mask.png")
            Image.fromarray(template).save(template_path)
            mask.save(mask_path)
            result = _match_template_image(
                cv2,
                np,
                Image,
                screen,
                template_path,
                0.6,
                "masked_edge",
                mask_path,
                40,
                120,
                "",
            )

        self.assertGreaterEqual(result.score, 0.6)
        self.assertEqual((result.x, result.y), (48, 35))
        self.assertEqual(result.match_mode, "masked_edge")
    def test_failed_match_keeps_best_candidate_preview(self):
        import cv2
        import numpy as np

        template = np.zeros((12, 12, 3), dtype=np.uint8)
        template[2:10, 5:7] = 255
        screen = np.zeros((30, 30, 3), dtype=np.uint8)

        with tempfile.TemporaryDirectory() as directory:
            template_path = os.path.join(directory, "template.png")
            Image.fromarray(template).save(template_path)
            with self.assertRaises(MatchFailure) as raised:
                _match_template_image(
                    cv2,
                    np,
                    Image,
                    screen,
                    template_path,
                    0.99,
                    "edge",
                    "",
                    40,
                    120,
                    "",
                )

        self.assertIsNotNone(raised.exception.result)
        self.assertTrue(raised.exception.result.preview_data_url.startswith("data:image/jpeg;base64,"))


class RegionSelectorTests(unittest.TestCase):
    def test_converts_desktop_region_to_target_window_coordinates(self):
        selector = RegionSelector(
            config_provider=lambda: {"window_hint": "逆水寒"},
            find_target_window=lambda _hint: {"hwnd": 42},
            window_rect_provider=lambda _hwnd: (100, 80, 1380, 800),
        )

        result = selector._make_window_relative(
            {"cancelled": False, "x": 320, "y": 210, "width": 400, "height": 240}
        )

        self.assertEqual(
            result,
            {"cancelled": False, "x": 220, "y": 130, "width": 400, "height": 240},
        )
    def test_focuses_target_and_limits_overlay_to_client_area(self):
        focused = []
        overlays = []
        selector = RegionSelector(
            config_provider=lambda: {"window_hint": "逆水寒"},
            find_target_window=lambda _hint: {"hwnd": 42},
            window_rect_provider=lambda _hwnd: (100, 80, 1380, 800),
            client_rect_provider=lambda _hwnd: (108, 111, 1372, 792),
            focus_target_window=focused.append,
            overlay=lambda bounds: overlays.append(bounds) or {
                "cancelled": False,
                "x": 320,
                "y": 210,
                "width": 400,
                "height": 240,
            },
        )

        result = selector.select()

        self.assertEqual(focused, [42])
        self.assertEqual(overlays, [(108, 111, 1372, 792)])
        self.assertEqual((result["x"], result["y"]), (220, 130))

    def test_missing_configured_window_reports_clear_error(self):
        selector = RegionSelector(
            config_provider=lambda: {"window_hint": "逆水寒"},
            find_target_window=lambda _hint: None,
        )

        with self.assertRaisesRegex(RuntimeError, "找不到目标窗口"):
            selector.select()


if __name__ == "__main__":
    unittest.main()
