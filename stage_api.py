import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace


DEFAULT_STAGE_API_CONFIG = {
    "base_url": "http://hapi.hi.163.com/nshm/action-station/work/list/search",
    "role_id": "",
    "user_id": "",
    "skey": "",
    "sort": "",
    "page_size": "20",
    "contents": "",
    "sub_types": "",
    "actor_count_contents": "",
    "work_filter": "single",
}


class StageApiError(RuntimeError):
    pass


@dataclass
class StageWork:
    work_id: int
    name: str
    summary: str
    designer_name: str
    hot: int
    like_count: int
    collect_count: int
    property_url: str
    cover_url: str = ""
    work_type: int = 0
    sub_type: int = 0
    actor_count: int = 0
    contents: tuple = ()
    duration_seconds: int = 0
    raw_duration: float = 0.0

    @property
    def category_label(self):
        if self.work_type == 1 and self.sub_type == 1 and self.actor_count <= 1:
            return "单人"
        if self.actor_count > 1 or self.sub_type == 3:
            return f"多人({self.actor_count or '-'})"
        if self.work_type == 3 or self.sub_type >= 100:
            return "映画/翻拍"
        return f"type{self.work_type}/sub{self.sub_type}"


def normalize_config(config):
    merged = dict(DEFAULT_STAGE_API_CONFIG)
    if isinstance(config, dict):
        for key in merged:
            merged[key] = str(config.get(key, merged[key]) or "")
    if not merged["page_size"]:
        merged["page_size"] = DEFAULT_STAGE_API_CONFIG["page_size"]
    if not merged["work_filter"]:
        merged["work_filter"] = DEFAULT_STAGE_API_CONFIG["work_filter"]
    return merged


def parse_stage_request_text(text, current_config=None):
    config = normalize_config(current_config)
    text = text or ""
    url_match = re.search(r"https?://[^\s'\"]+", text)
    if url_match:
        parsed = urllib.parse.urlsplit(url_match.group(0))
        config["base_url"] = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        params = urllib.parse.parse_qs(parsed.query)
        for key in ("role_id", "user_id", "sort", "page_size", "contents", "sub_types", "actor_count_contents"):
            if params.get(key):
                config[key] = params[key][0]
    skey_match = re.search(r"(?im)^\s*skey\s*[:=]\s*(\S+)", text)
    if skey_match:
        config["skey"] = skey_match.group(1).strip()
    return config


def search_works(keyword, config, page=1):
    keyword = (keyword or "").strip()
    if not keyword:
        raise StageApiError("请先输入搜索关键词")
    config = normalize_config(config)
    require_config(config, ["base_url", "role_id", "user_id", "skey"])
    params = {
        "page": str(page),
        "page_size": config["page_size"] or "20",
        "role_id": config["role_id"],
        "user_id": config["user_id"],
        "keyword": keyword,
        "actor_type_contents": "",
        "sort": config.get("sort", ""),
        "contents": config.get("contents", ""),
        "gender": "0",
        "publish_role": "0",
        "transform_type": "0",
        "actor_count_contents": config.get("actor_count_contents", ""),
        "sub_types": config.get("sub_types", ""),
        "is_original_camera": "0",
    }
    payload = fetch_json(build_url(config["base_url"], params), config)
    if int(payload.get("code", -1)) != 0:
        raise StageApiError(payload.get("message") or "搜索接口返回失败")
    items = payload.get("data", {}).get("list", [])
    works = [work_from_item(item) for item in items]
    works = filter_works(works, config.get("work_filter", "single"))
    return sorted(works, key=lambda work: match_sort_key(keyword, work), reverse=True)


def filter_works(works, work_filter):
    if work_filter == "all":
        return works
    if work_filter == "single":
        return [work for work in works if work.work_type == 1 and work.sub_type == 1 and work.actor_count <= 1]
    if work_filter == "multi":
        return [work for work in works if work.actor_count > 1 or work.sub_type == 3]
    if work_filter == "movie":
        return [work for work in works if work.work_type == 3 or work.sub_type >= 100]
    return works


def fill_work_duration(work):
    if not work.property_url:
        return work
    meta = fetch_json(work.property_url, {})
    duration = first_number(meta, ["actionTime", "speechTime", "cameraTime", "expressionTime"])
    if duration <= 0:
        duration = max_number(meta, ["actionTime", "speechTime", "cameraTime", "expressionTime"])
    work.raw_duration = duration
    work.duration_seconds = int(math.ceil(duration)) if duration > 0 else 0
    return work


def work_from_item(item):
    return StageWork(
        work_id=int(item.get("work_id", 0) or 0),
        name=str(item.get("name", "") or ""),
        summary=str(item.get("Summary", item.get("summary", "")) or ""),
        designer_name=str(item.get("designer_name", "") or ""),
        hot=int(item.get("hot", 0) or 0),
        like_count=int(item.get("like_count", 0) or 0),
        collect_count=int(item.get("collect_count", 0) or 0),
        property_url=str(item.get("property", "") or ""),
        cover_url=str(item.get("cover", "") or ""),
        work_type=int(item.get("type", 0) or 0),
        sub_type=int(item.get("sub_type", 0) or 0),
        actor_count=int(item.get("actor_count", 0) or 0),
        contents=tuple(item.get("contents", []) or ()),
    )


def match_sort_key(keyword, work):
    name = work.name.strip().lower()
    query = keyword.strip().lower()
    exact = 3 if name == query else 0
    starts = 2 if query and name.startswith(query) else 0
    contains = 1 if query and query in name else 0
    return exact + starts + contains, work.hot, work.collect_count, work.like_count


def build_url(base_url, params):
    return base_url + "?" + urllib.parse.urlencode(params)


def fetch_json(url, config):
    data = fetch_bytes(url, config)
    try:
        return json.loads(data.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise StageApiError("响应不是有效 JSON") from exc


def fetch_bytes(url, config=None):
    headers = {
        "User-Agent": "UnityPlayer/2020.3.26f1 (UnityWebRequest/1.0, libcurl/7.77.0-DEV)",
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "X-Unity-Version": "2020.3.26f1",
    }
    skey = str(config.get("skey", "") or "").strip() if isinstance(config, dict) else ""
    if skey:
        headers["skey"] = skey
        headers["x-nshm-server-time"] = str(int(time.time()))
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read(256).decode("utf-8", errors="replace")
        raise StageApiError(f"HTTP {exc.code}: {body or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise StageApiError(f"请求失败：{exc.reason}") from exc


def require_config(config, keys):
    missing = [key for key in keys if not str(config.get(key, "") or "").strip()]
    if missing:
        raise StageApiError("请先填写剧组接口配置：" + "、".join(missing))


def first_number(data, keys):
    for key in keys:
        value = data.get(key) if isinstance(data, dict) else None
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 0.0


def max_number(data, keys):
    values = []
    if not isinstance(data, dict):
        return 0.0
    for key in keys:
        try:
            values.append(float(data.get(key, 0) or 0))
        except (TypeError, ValueError):
            pass
    return max(values) if values else 0.0
