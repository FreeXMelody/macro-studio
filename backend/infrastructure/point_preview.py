import ctypes
import subprocess
import sys
import threading
from ctypes import wintypes


try:
    # Point definitions use physical screen pixels; the overlay must use the same
    # coordinate space on scaled and mixed-DPI displays.
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    pass


class PointPreviewService:
    def __init__(self, renderer=None):
        self.renderer = renderer or self._launch_overlay
        self._lock = threading.Lock()
        self._thread = None

    def preview(self, name, x, y, duration=2.6):
        name = str(name or "").strip()
        if not name:
            raise ValueError("点位名称不能为空")
        try:
            x = int(x)
            y = int(y)
            duration = float(duration)
        except (TypeError, ValueError) as exc:
            raise ValueError("点位坐标和预览时长格式无效") from exc
        if not 0.5 <= duration <= 10.0:
            raise ValueError("预览时长必须在 0.5 到 10 秒之间")
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("已有点位预览正在显示")

        self._thread = threading.Thread(
            target=self._render,
            args=(name, x, y, duration),
            name="macro-studio-point-preview",
            daemon=True,
        )
        self._thread.start()
        return {
            "status": "showing",
            "name": name,
            "x": x,
            "y": y,
            "duration": duration,
        }

    def flash(self, name, x, y, duration=0.85):
        name, x, y, duration = self._validated(name, x, y, duration)
        threading.Thread(
            target=self._render_flash,
            args=(name, x, y, duration),
            name="macro-studio-click-preview",
            daemon=True,
        ).start()

    @staticmethod
    def _validated(name, x, y, duration):
        name = str(name or "").strip()
        if not name:
            raise ValueError("点位名称不能为空")
        try:
            x = int(x)
            y = int(y)
            duration = float(duration)
        except (TypeError, ValueError) as exc:
            raise ValueError("点位坐标和预览时长格式无效") from exc
        if not 0.5 <= duration <= 10.0:
            raise ValueError("预览时长必须在 0.5 到 10 秒之间")
        return name, x, y, duration

    def join(self, timeout=None):
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _render_flash(self, name, x, y, duration):
        try:
            self.renderer(name, x, y, duration)
        except Exception:
            # Click visualization is diagnostic and must never interrupt a macro.
            pass

    def _render(self, name, x, y, duration):
        try:
            self.renderer(name, x, y, duration)
        finally:
            self._lock.release()

    @staticmethod
    def _launch_overlay(name, x, y, duration):
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            [
                sys.executable,
                __file__,
                "--overlay",
                name,
                str(x),
                str(y),
                str(duration),
            ],
            capture_output=True,
            text=True,
            creationflags=creationflags,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or f"退出码 {result.returncode}"
            raise RuntimeError(f"点位预览浮层启动失败：{detail}")

    @staticmethod
    def _show_overlay(name, x, y, duration):
        import tkinter as tk

        user32 = ctypes.windll.user32
        virtual_left = user32.GetSystemMetrics(76)
        virtual_top = user32.GetSystemMetrics(77)
        virtual_width = user32.GetSystemMetrics(78)
        virtual_height = user32.GetSystemMetrics(79)
        if virtual_width <= 0 or virtual_height <= 0:
            raise RuntimeError("无法读取桌面尺寸")

        root = tk.Tk()
        root.withdraw()
        overlay = tk.Toplevel(root)
        overlay.overrideredirect(True)
        overlay.configure(bg="#010203")
        overlay.geometry(f"{virtual_width}x{virtual_height}{virtual_left:+d}{virtual_top:+d}")
        overlay.attributes("-topmost", True)
        try:
            overlay.attributes("-transparentcolor", "#010203")
        except tk.TclError:
            pass

        canvas = tk.Canvas(overlay, bg="#010203", highlightthickness=0, borderwidth=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        overlay.deiconify()
        overlay.update_idletasks()
        hwnd = int(overlay.winfo_id())

        gwl_exstyle = -20
        ws_ex_transparent = 0x00000020
        ws_ex_toolwindow = 0x00000080
        ws_ex_noactivate = 0x08000000
        swp_noactivate = 0x0010
        swp_showwindow = 0x0040
        hwnd_topmost = -1
        styles = user32.GetWindowLongW(hwnd, gwl_exstyle)
        user32.SetWindowLongW(
            hwnd,
            gwl_exstyle,
            styles | ws_ex_transparent | ws_ex_toolwindow | ws_ex_noactivate,
        )
        user32.SetWindowPos(
            hwnd,
            hwnd_topmost,
            virtual_left,
            virtual_top,
            virtual_width,
            virtual_height,
            swp_noactivate | swp_showwindow,
        )

        center_x = int(x - virtual_left)
        center_y = int(y - virtual_top)
        accent = "#65e5bf"
        soft = "#a8f3dc"
        canvas.create_line(center_x - 42, center_y, center_x - 10, center_y, fill=accent, width=3)
        canvas.create_line(center_x + 10, center_y, center_x + 42, center_y, fill=accent, width=3)
        canvas.create_line(center_x, center_y - 42, center_x, center_y - 10, fill=accent, width=3)
        canvas.create_line(center_x, center_y + 10, center_x, center_y + 42, fill=accent, width=3)
        canvas.create_oval(center_x - 5, center_y - 5, center_x + 5, center_y + 5, outline="#ffffff", width=2)
        pulse = canvas.create_oval(center_x - 17, center_y - 17, center_x + 17, center_y + 17, outline=soft, width=2)

        label_x = center_x + 54
        anchor = "nw"
        if label_x + 250 > virtual_width:
            label_x = center_x - 54
            anchor = "ne"
        label_y = max(12, min(center_y + 22, virtual_height - 68))
        text_id = canvas.create_text(
            label_x,
            label_y,
            text=f"{name}\nX {x}   Y {y}",
            fill="#f4fffb",
            font=("Microsoft YaHei UI", 12, "bold"),
            anchor=anchor,
            justify=tk.LEFT,
        )
        bounds = canvas.bbox(text_id)
        if bounds:
            background = canvas.create_rectangle(
                bounds[0] - 12,
                bounds[1] - 8,
                bounds[2] + 12,
                bounds[3] + 8,
                fill="#14231f",
                outline="#65e5bf",
                width=1,
            )
            canvas.tag_lower(background, text_id)

        frame = {"value": 0}
        total_ms = int(duration * 1000)
        elapsed = {"value": 0}

        def animate():
            elapsed["value"] += 55
            frame["value"] += 1
            radius = 17 + (frame["value"] % 12) * 1.1
            canvas.coords(pulse, center_x - radius, center_y - radius, center_x + radius, center_y + radius)
            if elapsed["value"] >= total_ms:
                overlay.destroy()
                root.quit()
                return
            overlay.after(55, animate)

        overlay.after(55, animate)
        root.mainloop()
        try:
            root.destroy()
        except tk.TclError:
            pass


def _main():
    if len(sys.argv) != 6 or sys.argv[1] != "--overlay":
        raise SystemExit("usage: point_preview.py --overlay NAME X Y DURATION")
    PointPreviewService._show_overlay(
        sys.argv[2],
        int(sys.argv[3]),
        int(sys.argv[4]),
        float(sys.argv[5]),
    )


if __name__ == "__main__":
    _main()
