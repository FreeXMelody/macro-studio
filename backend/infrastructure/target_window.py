import base64
import ctypes
import io
import os
import threading
from ctypes import wintypes

from automation import find_window, get_process_integrity


class TargetWindowInspector:
    def __init__(self, config_provider, find_target_window=find_window):
        self.config_provider = config_provider
        self.find_target_window = find_target_window

    def probe(self, window_hint="", capture=False):
        hint = str(window_hint or "").strip()
        if not hint:
            hint = str(self.config_provider().get("window_hint", "")).strip()
        window = self.find_target_window(hint) if hint else None
        if not window:
            return {
                "found": False,
                "window_hint": hint,
                "error": f"找不到目标窗口：{hint or '未设置窗口关键词'}",
            }

        hwnd = int(window["hwnd"])
        rect = wintypes.RECT()
        client = wintypes.RECT()
        origin = wintypes.POINT(0, 0)
        user32 = ctypes.windll.user32
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise RuntimeError("无法读取目标窗口尺寸")
        if not user32.GetClientRect(hwnd, ctypes.byref(client)):
            raise RuntimeError("无法读取目标客户区尺寸")
        user32.ClientToScreen(hwnd, ctypes.byref(origin))
        dpi = int(user32.GetDpiForWindow(hwnd)) if hasattr(user32, "GetDpiForWindow") else 96
        target_integrity = get_process_integrity(int(window.get("pid", 0)))
        app_integrity = get_process_integrity(os.getpid())
        input_allowed = (
            not target_integrity["known"]
            or not app_integrity["known"]
            or target_integrity["rid"] <= app_integrity["rid"]
        )
        result = {
            "found": True,
            "window_hint": hint,
            "hwnd": hwnd,
            "pid": int(window.get("pid", 0)),
            "title": str(window.get("title", "")),
            "process_name": self._process_name(int(window.get("pid", 0))),
            "left": int(rect.left),
            "top": int(rect.top),
            "width": int(rect.right - rect.left),
            "height": int(rect.bottom - rect.top),
            "client_left": int(origin.x),
            "client_top": int(origin.y),
            "client_width": int(client.right - client.left),
            "client_height": int(client.bottom - client.top),
            "dpi": dpi,
            "minimized": bool(user32.IsIconic(hwnd)),
            "process_elevated": bool(target_integrity["elevated"]),
            "process_integrity": str(target_integrity["level"]),
            "app_elevated": bool(app_integrity["elevated"]),
            "app_integrity": str(app_integrity["level"]),
            "input_allowed": bool(input_allowed),
            "preview_data_url": "",
            "error": "",
        }
        if capture:
            preview, capture_width, capture_height = self._capture(hwnd)
            result["preview_data_url"] = preview
            result["capture_width"] = capture_width
            result["capture_height"] = capture_height
        return result

    def preflight(self):
        config = self.config_provider()
        settings = {
            "window_hint": str(config.get("window_hint", "")).strip(),
            "input_mode": str(config.get("input_mode", "foreground")).strip(),
            "focus_window": bool(config.get("focus_window", True)),
        }
        probe = self.probe(settings["window_hint"], capture=False)
        checks = [
            self._check("window_hint", "目标窗口关键词", bool(settings["window_hint"]), settings["window_hint"] or "尚未设置"),
            self._check("window_found", "目标窗口连接", probe["found"], probe.get("title") or probe.get("error", "未找到")),
        ]
        if probe["found"]:
            target_label = "管理员" if probe.get("process_elevated") else "普通"
            app_label = "管理员" if probe.get("app_elevated") else "普通"
            checks.append(
                self._check(
                    "input_permission",
                    "输入权限级别",
                    probe.get("input_allowed", True),
                    f"游戏：{target_label} / Macro Studio：{app_label}"
                    + ("" if probe.get("input_allowed", True) else "；请以管理员身份重启 Macro Studio"),
                )
            )
        checks.append(
            self._check(
                "input_mode",
                "输入模式",
                settings["input_mode"] in {"foreground", "window_message"},
                "后台窗口消息" if settings["input_mode"] == "window_message" else "前台输入",
            )
        )
        active_group = str(config.get("active_point_group", "")).strip()
        groups = config.get("point_groups", []) or []
        group_ok = bool(groups) and any(str(group.get("name", "")) == active_group for group in groups)
        checks.append(self._check("point_group", "活动点位组", group_ok, active_group or "尚未设置"))

        missing = []
        for target in config.get("image_targets", []) or []:
            template = str(target.get("template_path", "")).strip()
            mask = str(target.get("mask_path", "")).strip()
            if template and not os.path.exists(os.path.abspath(template)):
                missing.append(str(target.get("name", "未命名")) + " 模板")
            if mask and not os.path.exists(os.path.abspath(mask)):
                missing.append(str(target.get("name", "未命名")) + " 遮罩")
        checks.append(self._check("image_files", "图像资源", not missing, "全部可读" if not missing else "缺少：" + "、".join(missing[:3])))
        return {"ready": all(item["ok"] for item in checks), "checks": checks, "window": probe}

    @staticmethod
    def _check(key, label, ok, detail):
        return {"key": key, "label": label, "ok": bool(ok), "detail": str(detail)}

    @staticmethod
    def _process_name(pid):
        if not pid:
            return ""
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return ""
        try:
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return os.path.basename(buffer.value)
            return ""
        finally:
            kernel32.CloseHandle(handle)

    @staticmethod
    def _capture(hwnd):
        try:
            import cv2
            from PIL import Image
            from windows_capture import WindowsCapture
        except Exception as exc:
            raise RuntimeError("后台截图需要 windows-capture、Pillow 与 OpenCV") from exc
        done = threading.Event()
        holder = {}
        capture = WindowsCapture(
            cursor_capture=False,
            draw_border=False,
            window_hwnd=int(hwnd),
            minimum_update_interval=0,
        )

        @capture.event
        def on_frame_arrived(frame, control):
            holder["frame"] = frame.frame_buffer.copy()
            control.stop()
            done.set()

        @capture.event
        def on_closed():
            holder["error"] = "Windows Graphics Capture 已关闭"
            done.set()

        control = capture.start_free_threaded()
        if not done.wait(8):
            control.stop()
            raise RuntimeError("等待后台窗口截图超时")
        if "frame" not in holder:
            raise RuntimeError(holder.get("error", "未收到后台窗口截图"))
        rgb = cv2.cvtColor(holder["frame"][:, :, :3], cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        capture_width, capture_height = image.size
        max_edge = 1600
        if max(image.size) > max_edge:
            scale = max_edge / max(image.size)
            image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.Resampling.LANCZOS)
        stream = io.BytesIO()
        image.save(stream, format="JPEG", quality=82, optimize=True)
        return (
            "data:image/jpeg;base64," + base64.b64encode(stream.getvalue()).decode("ascii"),
            int(capture_width),
            int(capture_height),
        )
