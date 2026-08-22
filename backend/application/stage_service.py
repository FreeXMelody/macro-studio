import json
import mimetypes
import os
import tempfile
import threading
import time
import uuid
from urllib.parse import urlsplit

from stage_api import (
    DEFAULT_STAGE_API_CONFIG,
    StageApiError,
    fetch_bytes,
    fill_work_duration,
    normalize_config,
    parse_stage_request_text,
    search_works,
)
from stage_diagnostics import run_stage_diagnostics
from stage_http_listener import StageCaptureError, launch_elevated_capture


class StageService:
    """Owns stage-search configuration, result metadata, and auth capture state."""

    ALLOWED_HOST = "hapi.hi.163.com"
    SEARCH_PATH = "/nshm/action-station/work/list/search"

    def __init__(
        self,
        repository,
        *,
        searcher=search_works,
        duration_loader=fill_work_duration,
        byte_fetcher=fetch_bytes,
        capture_launcher=launch_elevated_capture,
        diagnostic_runner=run_stage_diagnostics,
        emit_log=None,
    ):
        self.repository = repository
        self.searcher = searcher
        self.duration_loader = duration_loader
        self.byte_fetcher = byte_fetcher
        self.capture_launcher = capture_launcher
        self.diagnostic_runner = diagnostic_runner
        self.emit_log = emit_log or (lambda _message: None)
        self._lock = threading.RLock()
        self._works = {}
        self._capture = self._empty_capture()
        self._diagnostics = self._empty_diagnostics()

    def document(self):
        data = self.repository.load()
        return {
            "config": normalize_config(data.get("stage_api", DEFAULT_STAGE_API_CONFIG)),
            "keyword": str(data.get("stage_search_keyword", "") or "").strip(),
        }

    def replace(self, config, keyword=""):
        normalized = normalize_config(config)
        self._validate_config_url(normalized["base_url"])
        keyword = str(keyword or "").strip()

        def mutate(data):
            data["stage_api"] = normalized
            data["stage_search_keyword"] = keyword

        self.repository.mutate(mutate)
        return {"config": normalized, "keyword": keyword}

    def parse_request(self, text):
        current = self.document()
        parsed = parse_stage_request_text(text, current["config"])
        self._validate_config_url(parsed["base_url"])
        return {"config": parsed, "keyword": current["keyword"]}

    def search(self, keyword, config=None, page=1, duration_limit=12, persist=True):
        current = self.document()
        normalized = normalize_config(config if config is not None else current["config"])
        self._validate_config_url(normalized["base_url"])
        keyword = str(keyword or "").strip()
        works = self.searcher(keyword, normalized, page=max(1, int(page)))
        for work in works[: max(0, int(duration_limit))]:
            try:
                self.duration_loader(work)
            except StageApiError:
                pass
        serialized = [self._serialize_work(work) for work in works]
        with self._lock:
            self._works = {item["work_id"]: item for item in serialized}
        if persist:
            self.replace(normalized, keyword)
        self.emit_log(f"剧组站搜索完成：{keyword}，找到 {len(serialized)} 个候选")
        return {"keyword": keyword, "page": max(1, int(page)), "works": serialized}

    def cover(self, work_id):
        with self._lock:
            work = self._works.get(int(work_id))
        if not work or not work.get("cover_url"):
            raise ValueError("封面不在当前搜索结果中")
        data = self.byte_fetcher(work["cover_url"], {})
        content_type = mimetypes.guess_type(urlsplit(work["cover_url"]).path)[0] or "image/jpeg"
        if not content_type.startswith("image/"):
            content_type = "image/jpeg"
        return data, content_type

    def start_capture(self, timeout=90):
        timeout = min(180, max(15, int(timeout)))
        with self._lock:
            if self._capture["status"] in {"listening", "validating"}:
                return self.capture_state()
            capture_id = uuid.uuid4().hex
            path = os.path.join(tempfile.gettempdir(), f"macro-studio-stage-{capture_id}.json")
            self._capture = {
                "status": "listening",
                "message": "正在监听游戏请求，请在游戏剧组站搜索一次作品。",
                "keyword": "",
                "config": None,
                "works": [],
                "deadline": time.time() + timeout,
                "path": path,
                "capture_id": capture_id,
            }
        try:
            self.capture_launcher(path, timeout=timeout)
        except StageCaptureError as exc:
            self._finish_capture("failed", f"监听启动失败：{exc}")
            return self.capture_state()
        threading.Thread(
            target=self._poll_capture,
            args=(capture_id, path),
            name="stage-auth-capture",
            daemon=True,
        ).start()
        return self.capture_state()

    def capture_state(self):
        with self._lock:
            return {
                "status": self._capture["status"],
                "message": self._capture["message"],
                "keyword": self._capture["keyword"],
                "config": self._capture["config"],
                "works": list(self._capture["works"]),
                "deadline": float(self._capture["deadline"] or 0),
            }

    def _poll_capture(self, capture_id, path):
        try:
            while True:
                with self._lock:
                    if self._capture["capture_id"] != capture_id:
                        return
                    deadline = self._capture["deadline"]
                if os.path.exists(path):
                    break
                if time.time() >= deadline:
                    self._finish_capture("failed", "监听超时，请重新监听后在游戏内执行一次作品搜索。")
                    return
                time.sleep(0.3)
            with open(path, "r", encoding="utf-8") as stream:
                payload = json.load(stream)
            if not payload.get("ok"):
                self._finish_capture("failed", f"监听失败：{payload.get('error') or '未知错误'}")
                return
            captured = dict(payload.get("config") or {})
            keyword = str(captured.pop("keyword", "") or "").strip()
            candidate = normalize_config(captured)
            self._validate_config_url(candidate["base_url"])
            with self._lock:
                self._capture.update(status="validating", message="已捕获请求，正在验证参数。")
            result = self.search(keyword, candidate, persist=True) if keyword else {"works": []}
            with self._lock:
                self._capture.update(
                    status="completed",
                    message=(
                        f"参数已捕获并验证，找到 {len(result['works'])} 个候选。"
                        if keyword
                        else "参数已捕获；请求中没有搜索关键词。"
                    ),
                    keyword=keyword,
                    config=candidate,
                    works=result["works"],
                )
            self.emit_log("剧组站登录参数已捕获并保存")
        except (OSError, ValueError, json.JSONDecodeError, StageApiError) as exc:
            self._finish_capture("failed", f"捕获参数验证失败：{exc}")
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def start_diagnostics(self):
        with self._lock:
            if self._diagnostics["status"] == "running":
                return self.diagnostics_state()
            self._diagnostics = {
                **self._empty_diagnostics(),
                "status": "running",
                "message": "正在扫描 WebView 缓存、游戏模块和最近日志。",
                "started_at": time.time(),
            }
        threading.Thread(
            target=self._run_diagnostics,
            name="stage-diagnostics",
            daemon=True,
        ).start()
        return self.diagnostics_state()

    def diagnostics_state(self):
        with self._lock:
            return {
                "status": self._diagnostics["status"],
                "message": self._diagnostics["message"],
                "summary": dict(self._diagnostics["summary"]),
                "notes": list(self._diagnostics["notes"]),
                "report": self._diagnostics["report"],
                "started_at": float(self._diagnostics["started_at"] or 0),
                "finished_at": float(self._diagnostics["finished_at"] or 0),
            }

    def _run_diagnostics(self):
        try:
            report = self.diagnostic_runner()
            summary = {
                "cache_files_seen": int(report.cache_files_seen),
                "cache_hits": len(report.cache_hits),
                "binary_hits": len(report.binary_hits),
                "method_candidates": len(report.method_candidates),
                "action_play_logs": len(report.action_play_logs),
                "qrcode_work_logs": len(report.qrcode_work_logs),
                "voice_playback_logs": len(report.voice_playback_logs),
            }
            with self._lock:
                self._diagnostics.update(
                    status="completed",
                    message="诊断完成。",
                    summary=summary,
                    notes=[str(note) for note in report.notes],
                    report=report.to_text(),
                    finished_at=time.time(),
                )
            self.emit_log("剧组站高级诊断已完成")
        except Exception as exc:
            with self._lock:
                self._diagnostics.update(
                    status="failed",
                    message=f"诊断失败：{exc}",
                    finished_at=time.time(),
                )
            self.emit_log("剧组站高级诊断失败")

    def _finish_capture(self, status, message):
        with self._lock:
            self._capture.update(status=status, message=str(message))

    @staticmethod
    def _empty_diagnostics():
        return {
            "status": "idle",
            "message": "尚未运行诊断。",
            "summary": {},
            "notes": [],
            "report": "",
            "started_at": 0.0,
            "finished_at": 0.0,
        }

    @staticmethod
    def _empty_capture():
        return {
            "status": "idle",
            "message": "尚未监听游戏请求。",
            "keyword": "",
            "config": None,
            "works": [],
            "deadline": 0.0,
            "path": "",
            "capture_id": "",
        }

    @classmethod
    def _validate_config_url(cls, url):
        parsed = urlsplit(str(url or ""))
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname != cls.ALLOWED_HOST
            or parsed.path != cls.SEARCH_PATH
        ):
            raise ValueError("剧组搜索接口地址不受信任")

    @staticmethod
    def _serialize_work(work):
        return {
            "work_id": int(work.work_id),
            "name": str(work.name),
            "summary": str(work.summary),
            "designer_name": str(work.designer_name),
            "hot": int(work.hot),
            "like_count": int(work.like_count),
            "collect_count": int(work.collect_count),
            "cover_url": str(work.cover_url),
            "category_label": str(work.category_label),
            "work_type": int(work.work_type),
            "sub_type": int(work.sub_type),
            "actor_count": int(work.actor_count),
            "duration_seconds": int(work.duration_seconds),
        }