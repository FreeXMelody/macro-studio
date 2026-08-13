import ctypes
import threading
import time
from ctypes import wintypes

from automation import find_window, focus_window


class RegionSelector:
    def __init__(
        self,
        config_provider=None,
        find_target_window=None,
        window_rect_provider=None,
        client_rect_provider=None,
        focus_target_window=None,
        overlay=None,
    ):
        self.config_provider = config_provider or (lambda: {})
        self.find_target_window = find_target_window or find_window
        self.window_rect_provider = window_rect_provider or self._window_rect
        self.client_rect_provider = client_rect_provider or self._client_screen_rect
        self.focus_target_window = focus_target_window or focus_window
        self.overlay = overlay or self._show_overlay
        self._active = threading.Lock()

    def select(self):
        if not self._active.acquire(blocking=False):
            raise RuntimeError("已经有一个选区操作正在进行")
        try:
            window = self._target_window()
            outer_rect = None
            client_rect = None
            if window:
                hwnd = int(window["hwnd"])
                outer_rect = self.window_rect_provider(hwnd)
                client_rect = self.client_rect_provider(hwnd)
                try:
                    self.focus_target_window(hwnd)
                except Exception:
                    pass
                time.sleep(0.18)
            result = self.overlay(client_rect)
            return self._make_window_relative(result, window=window, outer_rect=outer_rect)
        finally:
            self._active.release()

    def _target_window(self):
        config = self.config_provider()
        window_hint = str(config.get("window_hint", "")).strip() if isinstance(config, dict) else ""
        if not window_hint:
            return None
        window = self.find_target_window(window_hint)
        if not window:
            raise RuntimeError(f"找不到目标窗口：{window_hint}")
        return window

    def _make_window_relative(self, result, window=None, outer_rect=None):
        if result.get("cancelled"):
            return result
        if window is None:
            config = self.config_provider()
            window_hint = str(config.get("window_hint", "")).strip() if isinstance(config, dict) else ""
            window = self.find_target_window(window_hint) if window_hint else None
        if not window:
            return result
        if outer_rect is None:
            outer_rect = self.window_rect_provider(int(window["hwnd"]))
        left, top, _right, _bottom = outer_rect
        return {
            **result,
            "x": int(result["x"] - left),
            "y": int(result["y"] - top),
        }

    @staticmethod
    def _window_rect(hwnd):
        rect = wintypes.RECT()
        if not ctypes.windll.user32.GetWindowRect(int(hwnd), ctypes.byref(rect)):
            raise RuntimeError("无法读取目标窗口尺寸")
        return rect.left, rect.top, rect.right, rect.bottom

    @staticmethod
    def _client_screen_rect(hwnd):
        rect = wintypes.RECT()
        origin = wintypes.POINT(0, 0)
        if not ctypes.windll.user32.GetClientRect(int(hwnd), ctypes.byref(rect)):
            raise RuntimeError("无法读取目标客户区尺寸")
        if not ctypes.windll.user32.ClientToScreen(int(hwnd), ctypes.byref(origin)):
            raise RuntimeError("无法读取目标客户区位置")
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width <= 0 or height <= 0:
            raise RuntimeError("目标客户区尺寸无效")
        return origin.x, origin.y, origin.x + width, origin.y + height

    @staticmethod
    def _show_overlay(bounds=None):
        import tkinter as tk

        user32 = ctypes.windll.user32
        previous_dpi_context = None
        try:
            set_thread_dpi = user32.SetThreadDpiAwarenessContext
            set_thread_dpi.restype = ctypes.c_void_p
            previous_dpi_context = set_thread_dpi(ctypes.c_void_p(-4))
        except Exception:
            previous_dpi_context = None

        result = {"cancelled": True, "x": 0, "y": 0, "width": 0, "height": 0}
        root = tk.Tk()
        root.withdraw()
        overlay = tk.Toplevel(root)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        try:
            overlay.attributes("-alpha", 0.34)
        except tk.TclError:
            pass

        if bounds is None:
            left = int(user32.GetSystemMetrics(76))
            top = int(user32.GetSystemMetrics(77))
            width = int(user32.GetSystemMetrics(78))
            height = int(user32.GetSystemMetrics(79))
            if width <= 0 or height <= 0:
                left, top = 0, 0
                width = overlay.winfo_screenwidth()
                height = overlay.winfo_screenheight()
        else:
            left, top, right, bottom = [int(value) for value in bounds]
            width = right - left
            height = bottom - top
            if width <= 0 or height <= 0:
                raise RuntimeError("目标客户区尺寸无效")

        overlay.geometry(f"{width}x{height}{left:+d}{top:+d}")
        overlay.configure(bg="#050708")
        canvas = tk.Canvas(overlay, bg="#050708", highlightthickness=0, cursor="crosshair")
        canvas.pack(fill=tk.BOTH, expand=True)
        canvas.create_text(
            width // 2,
            38,
            text="拖拽选择识别区域，松开确认；Esc 或右键取消",
            fill="#ffffff",
            font=("Microsoft YaHei UI", 15, "bold"),
        )
        start = {"active": False, "root_x": 0, "root_y": 0, "canvas_x": 0, "canvas_y": 0}
        rectangle = {"id": None}

        def finish(cancelled=True, event=None):
            if event is not None and not cancelled and start["active"]:
                selected_left = min(start["root_x"], event.x_root)
                selected_top = min(start["root_y"], event.y_root)
                selected_width = abs(event.x_root - start["root_x"])
                selected_height = abs(event.y_root - start["root_y"])
                if selected_width >= 5 and selected_height >= 5:
                    result.update(
                        cancelled=False,
                        x=int(selected_left),
                        y=int(selected_top),
                        width=int(selected_width),
                        height=int(selected_height),
                    )
            overlay.destroy()
            root.quit()

        def begin(event):
            start.update(
                active=True,
                root_x=event.x_root,
                root_y=event.y_root,
                canvas_x=event.x,
                canvas_y=event.y,
            )
            if rectangle["id"] is not None:
                canvas.delete(rectangle["id"])
            rectangle["id"] = None

        def move(event):
            if not start["active"]:
                return
            if rectangle["id"] is not None:
                canvas.delete(rectangle["id"])
            rectangle["id"] = canvas.create_rectangle(
                start["canvas_x"],
                start["canvas_y"],
                event.x,
                event.y,
                outline="#70d4b8",
                width=3,
                fill="#14362d",
                stipple="gray25",
            )

        canvas.bind("<ButtonPress-1>", begin)
        canvas.bind("<B1-Motion>", move)
        canvas.bind("<ButtonRelease-1>", lambda event: finish(False, event))
        overlay.bind("<Escape>", lambda _event: finish())
        overlay.bind("<Button-3>", lambda _event: finish())
        overlay.update_idletasks()
        overlay.lift()
        overlay.focus_force()
        try:
            root.mainloop()
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass
            if previous_dpi_context:
                try:
                    user32.SetThreadDpiAwarenessContext(previous_dpi_context)
                except Exception:
                    pass
        return result
