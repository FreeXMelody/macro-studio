import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class RunnerStatus(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class RunnerEvent:
    kind: str
    status: RunnerStatus
    data: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "type": self.kind,
            "status": self.status.value,
            "data": dict(self.data),
        }


class RunnerControl:
    def __init__(self, stop_event=None, resume_event=None):
        self.stop_event = stop_event or threading.Event()
        self.resume_event = resume_event or threading.Event()
        self.resume_event.set()
        self._status = RunnerStatus.IDLE
        self._lock = threading.Lock()

    @property
    def status(self):
        with self._lock:
            return self._status

    @property
    def pause_event(self):
        return self.resume_event

    def reset(self):
        self.stop_event.clear()
        self.resume_event.set()
        self.transition(RunnerStatus.STARTING)

    def transition(self, status):
        with self._lock:
            self._status = RunnerStatus(status)

    def request_stop(self):
        if self.status not in {RunnerStatus.IDLE, RunnerStatus.STOPPED, RunnerStatus.COMPLETED, RunnerStatus.FAILED}:
            self.transition(RunnerStatus.STOPPING)
        self.stop_event.set()
        self.resume_event.set()

    def pause(self):
        if self.status in {RunnerStatus.STARTING, RunnerStatus.RUNNING}:
            self.resume_event.clear()
            self.transition(RunnerStatus.PAUSED)
            return True
        return False

    def resume(self):
        was_paused = self.status == RunnerStatus.PAUSED
        self.resume_event.set()
        if was_paused:
            self.transition(RunnerStatus.RUNNING)
        return was_paused

    def should_stop(self):
        return self.stop_event.is_set()

    def wait_until_runnable(self, poll_interval=0.1):
        while not self.should_stop():
            if self.resume_event.wait(poll_interval):
                return not self.should_stop()
        return False

    def wait(self, seconds, poll_interval=0.2):
        remaining = max(0.0, float(seconds))
        last_tick = time.monotonic()
        while remaining > 0:
            if self.should_stop():
                return False
            if not self.resume_event.is_set():
                self.resume_event.wait(poll_interval)
                last_tick = time.monotonic()
                continue
            if self.stop_event.wait(min(poll_interval, remaining)):
                return False
            now = time.monotonic()
            remaining -= now - last_tick
            last_tick = now
        return not self.should_stop()
