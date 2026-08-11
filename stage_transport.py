import json
import os
import shlex
import urllib.error
import urllib.request


class StageTransportError(RuntimeError):
    pass


def open_uri(uri):
    uri = (uri or "").strip()
    if not uri:
        raise StageTransportError("请填写要打开的链接或协议地址")
    try:
        os.startfile(uri)
    except OSError as exc:
        raise StageTransportError(f"无法打开：{uri}") from exc


def send_http_request(spec, timeout=5):
    method, url, body = parse_http_request_spec(spec)
    data = None
    headers = {"User-Agent": "MacroStudio/1.0"}
    if body:
        data = body.encode("utf-8")
        headers["Content-Type"] = "application/json" if looks_like_json(body) else "text/plain; charset=utf-8"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read(512).decode("utf-8", errors="replace")
            return response.status, response_body
    except urllib.error.HTTPError as exc:
        body = exc.read(512).decode("utf-8", errors="replace")
        raise StageTransportError(f"HTTP {exc.code}: {body or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise StageTransportError(f"请求失败：{exc.reason}") from exc


def parse_http_request_spec(spec):
    text = (spec or "").strip()
    if not text:
        raise StageTransportError("请填写请求，例如 GET http://127.0.0.1:端口/path")
    try:
        parts = shlex.split(text, posix=False)
    except ValueError as exc:
        raise StageTransportError(f"请求参数格式错误：{exc}") from exc
    if not parts:
        raise StageTransportError("请填写请求")
    if parts[0].upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        method = parts[0].upper()
        parts = parts[1:]
    else:
        method = "GET"
    if not parts:
        raise StageTransportError("请填写请求 URL")
    url = parts[0]
    body = " ".join(parts[1:]).strip()
    if not url.lower().startswith(("http://", "https://")):
        raise StageTransportError("HTTP 请求 URL 需要以 http:// 或 https:// 开头")
    return method, url, body


def looks_like_json(text):
    try:
        json.loads(text)
        return True
    except json.JSONDecodeError:
        return False
