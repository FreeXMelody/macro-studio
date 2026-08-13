import threading

from backend.infrastructure.json_storage import load_json, save_json


class ConfigRepository:
    """Serializes updates to the shared macro configuration document."""

    def __init__(self, path):
        self.path = path
        self._lock = threading.RLock()

    def load(self):
        with self._lock:
            return load_json(self.path, {}, document_type="macro_config")

    def mutate(self, mutator):
        with self._lock:
            document = load_json(self.path, {}, document_type="macro_config")
            if not isinstance(document, dict):
                document = {}
            mutator(document)
            save_json(self.path, document, document_type="macro_config")
            return document
