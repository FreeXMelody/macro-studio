import ctypes
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.application.sequence_runner import PreparedJob, RunnerJob
from backend.domain.runner import RunnerControl
from backend.infrastructure.emergency_hotkey import EmergencyStopMonitor
from backend.infrastructure.windows_executor import (
    WindowsActionExecutor,
    parse_execution_settings,
)
from automation import RECT, get_process_integrity
from models import Song, SongGroup, Step
from vision import MatchFailure, MatchResult
from utils import parse_duration


class Win32StructureTests(unittest.TestCase):
    def test_rect_matches_win32_layout(self):
        rect = RECT(1, 2, 3, 4)

        self.assertEqual((rect.left, rect.top, rect.right, rect.bottom), (1, 2, 3, 4))
        self.assertEqual(ctypes.sizeof(RECT), ctypes.sizeof(ctypes.c_long) * 4)

    def test_current_process_integrity_is_readable(self):
        info = get_process_integrity(os.getpid())

        self.assertTrue(info["known"])
        self.assertIn(info["level"], {"low", "medium", "high", "system"})
        self.assertGreater(info["rid"], 0)


class FakeBindings:
    def __init__(self):
        self.calls = []

    def find_window(self, hint):
        self.calls.append(("find_window", hint))
        return {"hwnd": 42, "title": "Game"}

    def focus_window(self, hwnd):
        self.calls.append(("focus_window", hwnd))
        return True

    def post_click_xy(self, hwnd, x, y):
        self.calls.append(("post_click_xy", hwnd, x, y))

    def post_click_window_xy(self, hwnd, x, y):
        self.calls.append(("post_click_window_xy", hwnd, x, y))

    def click_xy(self, x, y):
        self.calls.append(("click_xy", x, y))

    def window_to_screen_xy(self, hwnd, x, y):
        self.calls.append(("window_to_screen_xy", hwnd, x, y))
        return x + 1000, y + 500

    def post_key(self, hwnd, vk, is_down):
        self.calls.append(("post_key", hwnd, vk, is_down))

    def key_down(self, vk):
        self.calls.append(("key_down", vk))

    def key_up(self, vk):
        self.calls.append(("key_up", vk))

    def post_text(self, hwnd, text):
        self.calls.append(("post_text", hwnd, text))

    def set_clipboard_text(self, text):
        self.calls.append(("set_clipboard_text", text))

    def hotkey(self, keys):
        self.calls.append(("hotkey", tuple(keys)))

    def locate_template_in_window(self, path, hwnd, region, threshold, *options):
        self.calls.append(("locate_window", path, hwnd, region, threshold))
        return MatchResult(x=100, y=200, score=0.91, width=20, height=10)

    def locate_template(self, path, region, threshold, *options):
        self.calls.append(("locate", path, region, threshold))
        return MatchResult(x=100, y=200, score=0.91, width=20, height=10)

    def open_uri(self, value):
        self.calls.append(("open_uri", value))

    def send_http_request(self, value):
        self.calls.append(("http_request", value))
        return 204, ""


def make_job():
    song = Song(title="问爱", keyword="问爱", duration_seconds=30, buffer_seconds=5)
    return RunnerJob(song=song, group=SongGroup(name="古风", songs=[song]))


def make_prepared(steps):
    return PreparedJob(
        steps=steps,
        label="问爱",
        group_name="古风",
        preset_label="播放流程",
    )


class ExecutionSettingsTests(unittest.TestCase):
    def test_active_point_group_and_relative_template_are_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = parse_execution_settings(
                {
                    "active_point_group": "游戏",
                    "point_groups": [
                        {"name": "其他", "points": [{"name": "A", "x": 1, "y": 2}]},
                        {"name": "游戏", "points": [{"name": "播放", "x": 10, "y": 20}]},
                    ],
                    "image_targets": [
                        {"name": "按钮", "template_path": "images/button.png"},
                    ],
                    "input_mode": "window_message",
                },
                directory,
            )
        self.assertEqual((settings.points["播放"].x, settings.points["播放"].y), (10, 20))
        template_path = Path(settings.image_targets["按钮"].template_path)
        self.assertEqual(template_path.name, "button.png")
        self.assertEqual(template_path.parent.name, "images")
        self.assertEqual(settings.input_mode, "window_message")


class WindowsActionExecutorTests(unittest.TestCase):
    def make_executor(self, config, point_visualizer=None, integrity_reader=lambda _pid: {"known": False}):
        self.control = RunnerControl()
        self.control.reset()
        self.bindings = FakeBindings()
        self.logs = []
        return WindowsActionExecutor(
            self.control,
            config_provider=lambda: config,
            base_dir=str(Path.cwd()),
            emit_log=self.logs.append,
            bindings=self.bindings,
            point_visualizer=point_visualizer,
            integrity_reader=integrity_reader,
        )

    def test_prepare_rejects_lower_integrity_than_target_window(self):
        executor = self.make_executor(
            {
                "window_hint": "逆水寒",
                "focus_window": False,
                "input_mode": "window_message",
            },
            integrity_reader=lambda pid: {
                "known": True,
                "rid": 0x3000 if pid == 42 else 0x2000,
                "level": "high" if pid == 42 else "medium",
                "elevated": pid == 42,
            },
        )
        self.bindings.find_window = lambda hint: {"hwnd": 42, "pid": 42, "title": hint}

        with self.assertRaisesRegex(RuntimeError, "npm run dev:admin"):
            executor.prepare_job(make_job(), make_prepared([]))

    def test_window_message_click_uses_active_point_and_focuses_window(self):
        executor = self.make_executor(
            {
                "window_hint": "逆水寒",
                "focus_window": True,
                "input_mode": "window_message",
                "active_point_group": "游戏",
                "point_groups": [
                    {"name": "游戏", "points": [{"name": "播放", "x": 120, "y": 240}]}
                ],
            }
        )
        job = make_job()
        prepared = executor.prepare_job(job, make_prepared([]))
        executor.execute_step(Step("点击", "click", target="播放"), job, prepared)
        self.assertIn(("find_window", "逆水寒"), self.bindings.calls)
        self.assertIn(("focus_window", 42), self.bindings.calls)
        self.assertIn(("post_click_xy", 42, 120, 240), self.bindings.calls)

    def test_image_click_applies_offset_without_using_real_capture(self):
        executor = self.make_executor(
            {
                "window_hint": "逆水寒",
                "focus_window": False,
                "input_mode": "window_message",
                "image_targets": [
                    {
                        "name": "剧组站",
                        "template_path": "image_templates/stage.png",
                        "region": "1,2,300,200",
                        "threshold": 0.7,
                        "offset_x": 4,
                        "offset_y": -5,
                        "retry_seconds": 0,
                    }
                ],
            }
        )
        job = make_job()
        prepared = executor.prepare_job(job, make_prepared([]))
        executor.execute_step(Step("识别", "image_click", value="剧组站"), job, prepared)
        self.assertIn(("post_click_window_xy", 42, 104, 195), self.bindings.calls)
        self.assertNotIn(("post_click_xy", 42, 104, 195), self.bindings.calls)

    def test_image_click_dispatch_failure_is_not_reported_as_recognition_failure(self):
        executor = self.make_executor(
            {
                "window_hint": "逆水寒",
                "focus_window": False,
                "input_mode": "window_message",
                "image_targets": [
                    {
                        "name": "剧组站",
                        "template_path": "stage.png",
                        "retry_seconds": 2,
                    }
                ],
            }
        )
        job = make_job()
        prepared = executor.prepare_job(job, make_prepared([]))

        def fail_click(hwnd, x, y):
            self.bindings.calls.append(("failed_click", hwnd, x, y))
            raise RuntimeError("测试点击派发失败")

        self.bindings.post_click_window_xy = fail_click
        with self.assertRaisesRegex(RuntimeError, "图像已命中但点击失败.*测试点击派发失败"):
            executor.execute_step(Step("识别", "image_click", value="剧组站"), job, prepared)

        locate_calls = [call for call in self.bindings.calls if call[0] == "locate_window"]
        self.assertEqual(len(locate_calls), 1)
        self.assertIn("图像已命中：剧组站 (0.910)，准备点击 100, 200", self.logs)

    def test_image_click_logs_each_real_attempt_and_best_score(self):
        executor = self.make_executor(
            {
                "window_hint": "逆水寒",
                "focus_window": False,
                "input_mode": "window_message",
                "image_targets": [
                    {
                        "name": "剧组站",
                        "template_path": "stage.png",
                        "threshold": 0.7,
                        "retry_seconds": 1,
                    }
                ],
            }
        )
        job = make_job()
        prepared = executor.prepare_job(job, make_prepared([]))
        scores = iter((0.61, 0.66))

        def fail_match(*_args):
            score = next(scores)
            raise MatchFailure(
                f"后台截图未达到识别阈值：最高相似度 {score:.3f}，阈值 0.700",
                MatchResult(x=10, y=20, score=score, width=30, height=40),
            )

        self.bindings.locate_template_in_window = fail_match
        self.control.wait = lambda *_args, **_kwargs: True
        with patch(
            "backend.infrastructure.windows_executor.time.monotonic",
            side_effect=(10.0, 10.2, 11.1),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                r"实际尝试 2 次.*本轮最高相似度 0.660 / 阈值 0.700",
            ):
                executor.execute_step(
                    Step("识别", "image_click", value="剧组站"),
                    job,
                    prepared,
                )

        self.assertTrue(any("图像识别尝试 1 未命中" in log and "0.610" in log for log in self.logs))
        self.assertTrue(any("图像识别尝试 2 未命中" in log and "0.660" in log for log in self.logs))

    def test_point_click_preview_uses_physical_screen_coordinates(self):
        visualized = []
        executor = self.make_executor(
            {
                "window_hint": "逆水寒",
                "focus_window": False,
                "input_mode": "window_message",
                "preview_clicks": True,
                "active_point_group": "游戏",
                "point_groups": [
                    {"name": "游戏", "points": [{"name": "播放", "x": 1920, "y": 1080}]}
                ],
            },
            point_visualizer=lambda *args: visualized.append(args),
        )
        job = make_job()
        prepared = executor.prepare_job(job, make_prepared([]))
        executor.execute_step(Step("点击", "click", target="播放"), job, prepared)

        self.assertEqual(visualized, [("执行点击 · 播放", 1920, 1080, 0.85)])

    def test_window_image_preview_converts_to_screen_coordinates(self):
        visualized = []
        executor = self.make_executor(
            {
                "window_hint": "逆水寒",
                "focus_window": False,
                "input_mode": "window_message",
                "preview_clicks": True,
                "image_targets": [
                    {
                        "name": "按钮",
                        "template_path": "button.png",
                        "retry_seconds": 0,
                    }
                ],
            },
            point_visualizer=lambda *args: visualized.append(args),
        )
        job = make_job()
        prepared = executor.prepare_job(job, make_prepared([]))
        executor.execute_step(Step("识别", "image_click", value="按钮"), job, prepared)

        self.assertIn(("window_to_screen_xy", 42, 100, 200), self.bindings.calls)
        self.assertEqual(visualized, [("执行点击 · 按钮", 1100, 700, 0.85)])

    def test_key_hold_always_releases_key_when_stopped(self):
        executor = self.make_executor({"focus_window": False, "input_mode": "foreground"})
        job = make_job()
        prepared = executor.prepare_job(job, make_prepared([]))

        original_wait = self.control.wait

        def stop_on_wait(seconds, poll_interval=0.2):
            if seconds >= 0.5:
                self.control.request_stop()
                return False
            return original_wait(0, poll_interval)

        self.control.wait = stop_on_wait
        executor.execute_step(Step("长按", "key_hold", value="space@0.5"), job, prepared)
        self.assertIn(("key_down", 0x20), self.bindings.calls)
        self.assertIn(("key_up", 0x20), self.bindings.calls)

    def test_key_down_is_released_by_cleanup(self):
        executor = self.make_executor({"focus_window": False, "input_mode": "foreground"})
        job = make_job()
        prepared = executor.prepare_job(job, make_prepared([]))
        executor.execute_step(Step("按下", "key_down", value="space"), job, prepared)
        executor.cleanup()
        self.assertEqual(
            [call for call in self.bindings.calls if call[0] in {"key_down", "key_up"}],
            [("key_down", 0x20), ("key_up", 0x20)],
        )

    def test_paste_renders_song_variable_and_does_not_log_text(self):
        executor = self.make_executor({"focus_window": False, "input_mode": "foreground"})
        job = make_job()
        prepared = executor.prepare_job(job, make_prepared([]))
        executor.execute_step(Step("粘贴", "paste", value="{keyword}"), job, prepared)
        self.assertIn(("set_clipboard_text", "问爱"), self.bindings.calls)
        self.assertNotIn("问爱", " ".join(self.logs))
        self.assertIn("2 字符", self.logs[-1])

    def test_fractional_wait_after_is_applied_and_logged(self):
        executor = self.make_executor({"focus_window": False, "input_mode": "foreground"})
        job = make_job()
        prepared = executor.prepare_job(job, make_prepared([]))
        waits = []

        def record_wait(seconds, poll_interval=0.2):
            waits.append(seconds)
            return True

        self.control.wait = record_wait
        executor.execute_step(Step("记录", "log", value="完成", wait_after="0.5"), job, prepared)

        self.assertEqual(waits, [0.5, 0.08])
        self.assertIn("动作后等待 0.5 秒", self.logs)
        self.assertIn("动作后等待完成", self.logs)

    def test_duration_parser_preserves_fractional_seconds(self):
        self.assertEqual(parse_duration("0.5"), 0.5)
        self.assertEqual(parse_duration("01:02.5"), 62.5)


class EmergencyStopMonitorTests(unittest.TestCase):
    def test_poll_once_triggers_callback_without_starting_thread(self):
        calls = []
        monitor = EmergencyStopMonitor(lambda: calls.append("triggered"), is_pressed=lambda: True)
        self.assertTrue(monitor.poll_once())
        self.assertEqual(calls, ["triggered"])
if __name__ == "__main__":
    unittest.main()
