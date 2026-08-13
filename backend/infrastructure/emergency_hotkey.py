import threading
import time

from automation import VK_F9, user32


class EmergencyStopMonitor:
    def __init__(self, on_trigger, poll_interval=0.05, is_pressed=None):
        self.on_trigger = on_trigger
        self.poll_interval = max(0.01, float(poll_interval))
        self.is_pressed = is_pressed or (lambda: bool(user32.GetAsyncKeyState(VK_F9) & 1))
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="macro-studio-emergency-stop",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout=1.0):
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        self._thread = None

    def poll_once(self):
        if self.is_pressed():
            self.on_trigger()
            return True
        return False

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self.poll_once()
            except Exception:
                pass
            time.sleep(self.poll_interval)
