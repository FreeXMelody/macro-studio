import threading
import time
from copy import deepcopy

from automation import VK_F8, get_cursor_pos, user32


class PointCaptureMonitor:
    def __init__(self, poll_interval=0.05, is_pressed=None, get_position=None):
        self.poll_interval = max(0.01, float(poll_interval))
        self.is_pressed = is_pressed or (lambda: bool(user32.GetAsyncKeyState(VK_F8) & 1))
        self.get_position = get_position or get_cursor_pos
        self._state = {"status": "idle", "group_name": "", "point_name": "", "x": None, "y": None}
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="macro-studio-point-capture", daemon=True)
        self._thread.start()

    def stop(self, timeout=1.0):
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        self._thread = None

    def arm(self, group_name, point_name):
        group_name = str(group_name or "").strip()
        point_name = str(point_name or "").strip()
        if not group_name or not point_name:
            raise ValueError("点位组和点位名称不能为空")
        with self._lock:
            self._state = {
                "status": "armed",
                "group_name": group_name,
                "point_name": point_name,
                "x": None,
                "y": None,
            }
            return deepcopy(self._state)

    def cancel(self):
        with self._lock:
            self._state = {"status": "idle", "group_name": "", "point_name": "", "x": None, "y": None}
            return deepcopy(self._state)

    def state(self):
        with self._lock:
            return deepcopy(self._state)

    def poll_once(self):
        if not self.is_pressed():
            return False
        with self._lock:
            if self._state["status"] != "armed":
                return False
            x, y = self.get_position()
            self._state["status"] = "captured"
            self._state["x"] = int(x)
            self._state["y"] = int(y)
            return True

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self.poll_once()
            except Exception:
                pass
            time.sleep(self.poll_interval)