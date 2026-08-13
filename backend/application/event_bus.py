import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping

from backend.domain.runner import RunnerEvent


@dataclass(frozen=True)
class PublishedEvent:
    sequence: int
    timestamp: float
    type: str
    status: str
    data: Mapping[str, Any]

    def to_dict(self):
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "type": self.type,
            "status": self.status,
            "data": dict(self.data),
        }


class EventSubscription:
    def __init__(self, event_bus, subscription_id, event_queue):
        self._event_bus = event_bus
        self._subscription_id = subscription_id
        self._queue = event_queue
        self._closed = False

    def get(self, timeout=None):
        return self._queue.get(timeout=timeout)

    def close(self):
        if not self._closed:
            self._closed = True
            self._event_bus.unsubscribe(self._subscription_id)

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        self.close()


class EventBus:
    def __init__(self, subscriber_queue_size=256):
        self.subscriber_queue_size = max(1, int(subscriber_queue_size))
        self._lock = threading.Lock()
        self._subscribers = {}
        self._next_subscription_id = 1
        self._sequence = 0

    def subscribe(self):
        with self._lock:
            subscription_id = self._next_subscription_id
            self._next_subscription_id += 1
            event_queue = queue.Queue(maxsize=self.subscriber_queue_size)
            self._subscribers[subscription_id] = event_queue
        return EventSubscription(self, subscription_id, event_queue)

    def unsubscribe(self, subscription_id):
        with self._lock:
            self._subscribers.pop(subscription_id, None)

    def publish(self, event):
        payload = event.to_dict() if isinstance(event, RunnerEvent) else dict(event)
        with self._lock:
            self._sequence += 1
            published = PublishedEvent(
                sequence=self._sequence,
                timestamp=time.time(),
                type=str(payload.get("type", "event")),
                status=str(payload.get("status", "")),
                data=dict(payload.get("data") or {}),
            )
            subscribers = list(self._subscribers.values())
        for event_queue in subscribers:
            self._put_latest(event_queue, published)
        return published

    @staticmethod
    def _put_latest(event_queue, event):
        try:
            event_queue.put_nowait(event)
            return
        except queue.Full:
            pass
        try:
            event_queue.get_nowait()
        except queue.Empty:
            pass
        try:
            event_queue.put_nowait(event)
        except queue.Full:
            pass
