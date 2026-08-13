import json
import os
import shutil
import tempfile


CURRENT_SCHEMA_VERSION = 1
SCHEMA_KEY = "_schema_version"
DOCUMENT_KEY = "_document_type"


def load_json(path, fallback, document_type=None):
    if not os.path.exists(path):
        return fallback
    try:
        with open(path, "r", encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, json.JSONDecodeError):
        return fallback
    if not isinstance(data, dict):
        return data
    try:
        schema_version = int(data.get(SCHEMA_KEY, 0) or 0)
    except (TypeError, ValueError):
        return fallback
    if schema_version > CURRENT_SCHEMA_VERSION:
        return fallback
    stored_type = str(data.get(DOCUMENT_KEY, "") or "")
    if document_type and stored_type and stored_type != document_type:
        return fallback
    payload = dict(data)
    payload.pop(SCHEMA_KEY, None)
    payload.pop(DOCUMENT_KEY, None)
    return payload


def save_json(path, data, document_type=None):
    payload = data
    if document_type:
        if not isinstance(data, dict):
            raise TypeError("版本化 JSON 文档必须使用对象作为根节点")
        payload = dict(data)
        payload[SCHEMA_KEY] = CURRENT_SCHEMA_VERSION
        payload[DOCUMENT_KEY] = str(document_type)

    absolute_path = os.path.abspath(path)
    directory = os.path.dirname(absolute_path) or os.getcwd()
    os.makedirs(directory, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, prefix=os.path.basename(absolute_path) + ".", suffix=".tmp", delete=False) as stream:
            temp_path = stream.name
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if os.path.exists(absolute_path):
            shutil.copy2(absolute_path, absolute_path + ".bak")
        os.replace(temp_path, absolute_path)
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
