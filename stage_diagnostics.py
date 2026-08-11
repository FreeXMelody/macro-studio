import base64
import json
import os
import re
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_GAME_DIR = Path(r"L:\Netease\nshm\game")
DEFAULT_WEBVIEW_CACHE_DIR = Path.home() / r"AppData\Roaming\Netease\Mpay\MWSlocalStorage\ngwebview"

BRIDGE_TERMS = (
    "unisdk_js_native_call",
    "UniSDKJSBridge",
    "mwsInvoke",
    "methodId",
    "nativeCallback",
    "RegisterMethodIdList",
    "execute_extend_func",
    "NGWebViewCallbackToWeb",
    "ngwebview_notify_native",
    "openBrowser",
    "closeWebView",
    "ntOpenGMPage",
    "gmbridge_call_js",
    "gmbridge_clear_cache",
)

STAGE_TERMS = (
    "action-station",
    "work/list/search",
    "dress/list/recommend",
    "work_id",
    "workId",
    "previewWork",
    "playWork",
    "openWork",
    "playAction",
    "stage",
    "theater",
    "dance",
    "cooperate",
    "team",
    "剧组",
    "作品",
    "预览",
    "共演",
)

PLAYER_TERMS = (
    "MLiveCCPlayerImpl",
    "Invoke cmd = Play",
    "videoinfo",
    "ntStopPlayback",
    "StopPlayback",
    "Playback",
)

URL_RE = re.compile(r"https?://[^\x00\s\"'<>\\]{6,260}")
METHOD_VALUE_RE = re.compile(r"[\"']?methodId[\"']?\s*(?:===|==|:|=)\s*[\"']([A-Za-z0-9_./:-]{2,96})[\"']")
METHOD_WORD_RE = re.compile(r"\b(?:nt|gmbridge|ngwebview|NGWebView|MpayWebviewSupport|NeteaseMpayJSBridge)[A-Za-z0-9_]{2,96}\b")
PLAY_WORD_RE = re.compile(r"\b[A-Za-z0-9_]*(?:Play|Playback|Preview|Dance|Action|Work|Open|Start|Stop)[A-Za-z0-9_]*\b")
WORK_ID_RE = re.compile(r"\bworkId_[0-9]+\b")


@dataclass
class DiagnosticFileHit:
    path: str
    size: int
    terms: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    snippets: list[str] = field(default_factory=list)


@dataclass
class DiagnosticReport:
    cache_root: str
    game_dir: str
    cache_files_seen: int = 0
    cache_hits: list[DiagnosticFileHit] = field(default_factory=list)
    binary_hits: list[DiagnosticFileHit] = field(default_factory=list)
    exports: dict[str, list[str]] = field(default_factory=dict)
    log_hits: list[str] = field(default_factory=list)
    method_candidates: list[str] = field(default_factory=list)
    action_play_logs: list[str] = field(default_factory=list)
    qrcode_work_logs: list[str] = field(default_factory=list)
    voice_playback_logs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_text(self):
        lines = [
            "Macro Studio 剧组诊断报告",
            "=" * 32,
            f"WebView 缓存：{self.cache_root}",
            f"游戏目录：{self.game_dir}",
            "",
            f"缓存候选文件：{self.cache_files_seen}",
            f"缓存命中：{len(self.cache_hits)}",
            f"二进制命中：{len(self.binary_hits)}",
            f"候选方法名：{len(self.method_candidates)}",
            f"剧组播放日志：{len(self.action_play_logs)}",
            f"workId 二维码日志：{len(self.qrcode_work_logs)}",
            f"语音 Playback 日志：{len(self.voice_playback_logs)}",
            "",
        ]
        if self.notes:
            lines.extend(["结论 / 提示", "-" * 16])
            lines.extend(f"- {note}" for note in self.notes)
            lines.append("")
        if self.method_candidates:
            lines.extend(["候选 method / bridge 名称", "-" * 16])
            for name in self.method_candidates[:160]:
                lines.append(f"- {name}")
            lines.append("")
        if self.action_play_logs:
            lines.extend(["剧组/动作播放日志", "-" * 16])
            lines.extend(self.action_play_logs[:80])
            lines.append("")
        if self.qrcode_work_logs:
            lines.extend(["workId 二维码入口日志", "-" * 16])
            lines.extend(self.qrcode_work_logs[:120])
            lines.append("")
        if self.voice_playback_logs:
            lines.extend(["语音 Playback 日志", "-" * 16])
            lines.extend(self.voice_playback_logs[:80])
            lines.append("")
        if self.cache_hits:
            lines.extend(["WebView 缓存命中", "-" * 16])
            for hit in self.cache_hits[:30]:
                lines.extend(format_hit(hit))
            lines.append("")
        if self.binary_hits:
            lines.extend(["游戏模块命中", "-" * 16])
            for hit in self.binary_hits:
                lines.extend(format_hit(hit))
            lines.append("")
        if self.exports:
            lines.extend(["关键导出表", "-" * 16])
            for name, exports in self.exports.items():
                lines.append(f"{name}: {', '.join(exports) if exports else '无导出'}")
            lines.append("")
        if self.log_hits:
            lines.extend(["最近播放/桥接日志", "-" * 16])
            lines.extend(self.log_hits[:120])
            lines.append("")
        return "\n".join(lines).strip() + "\n"


def run_stage_diagnostics(cache_root=None, game_dir=None, max_cache_files=600):
    cache_root = Path(cache_root) if cache_root else DEFAULT_WEBVIEW_CACHE_DIR
    game_dir = Path(game_dir) if game_dir else DEFAULT_GAME_DIR
    report = DiagnosticReport(str(cache_root), str(game_dir))

    report.cache_hits, report.cache_files_seen = scan_webview_cache(cache_root, max_cache_files)
    report.binary_hits = scan_game_binaries(game_dir)
    report.exports = scan_key_exports(game_dir)
    report.log_hits, report.action_play_logs = scan_recent_logs(game_dir / "log")
    unisdk_rows, qrcode_rows, voice_rows = scan_unisdk_log(game_dir)
    report.log_hits.extend(unisdk_rows)
    report.qrcode_work_logs = qrcode_rows
    report.voice_playback_logs = voice_rows
    report.method_candidates = collect_method_candidates(report.cache_hits, report.binary_hits, report.log_hits)
    report.notes = build_notes(report)
    return report


def scan_webview_cache(root, max_files=600):
    subdirs = [
        root / "Code Cache" / "js",
        root / "Service Worker" / "CacheStorage",
        root / "Service Worker" / "ScriptCache",
        root / "Cache" / "Cache_Data",
    ]
    candidates = []
    for subdir in subdirs:
        if not subdir.exists():
            continue
        for dirpath, _dirnames, names in os.walk(subdir):
            for name in names:
                path = Path(dirpath) / name
                try:
                    stat = path.stat()
                except OSError:
                    continue
                if 0 < stat.st_size <= 8_000_000:
                    candidates.append((stat.st_mtime, stat.st_size, path))
    candidates.sort(reverse=True)
    hits = []
    terms = BRIDGE_TERMS + STAGE_TERMS + PLAYER_TERMS + ("CONTINUE_PLAY_LIST", "CONTINUE_PLAY_STATE", "ds-website-continue-play-switch")
    for _mtime, size, path in candidates[:max_files]:
        hit = scan_text_file(path, root, terms, size=size)
        if hit:
            hits.append(hit)
    return hits, len(candidates)


def scan_game_binaries(game_dir):
    names = (
        "NtUniSdkNgWebview.dll",
        "NtUniSdkGMBridge.dll",
        "NtUniSdkExtend.dll",
        "mpay.dll",
        "webview_support_helper.dll",
        "UnityPlayer.dll",
        "GameAssembly.dll",
    )
    hits = []
    terms = BRIDGE_TERMS + STAGE_TERMS + PLAYER_TERMS + ("remote-debugging-port", "devtools", "cef904430")
    for name in names:
        path = game_dir / name
        if not path.exists():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        found = []
        snippets = []
        for term in terms:
            if contains_term(data, term):
                found.append(term)
                if len(snippets) < 6:
                    snippet = snippet_for_binary(data, term)
                    if snippet:
                        snippets.append(snippet)
        if found:
            hits.append(DiagnosticFileHit(str(path), len(data), found, extract_urls(data), snippets))
    return hits


def scan_key_exports(game_dir):
    exports = {}
    for name in ("NtUniSdkNgWebview.dll", "NtUniSdkGMBridge.dll", "mpay.dll", "webview_support_helper.dll"):
        path = game_dir / name
        if path.exists():
            exports[name] = pe_exports(path)[:80]
    return exports


def scan_recent_logs(log_dir):
    if not log_dir.exists():
        return []
    patterns = (
        "unisdk_js_native_call",
        "onJsBridgeCall",
        "methodId",
        "ntOpenGMPage",
        "execute_extend_func",
        "ntStopPlayback",
        "StopPlayback",
        "StartPlayback",
        "MLiveCCPlayerImpl",
        "Invoke cmd = Play",
        "videoinfo",
        "l36-action",
        "action.fp.ps.netease.com",
        "action-station",
        "work/list/search",
    )
    log_files = sorted((p for p in log_dir.glob("*.log") if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)[:8]
    rows = []
    action_rows = []
    for path in log_files:
        try:
            text = path.read_text("utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            if any(pattern in line for pattern in patterns):
                decoded = decode_videoinfo_from_line(line)
                display = f"{path.name}: {line[:480]}"
                if decoded:
                    display += f"\n  decoded_videoinfo: {decoded}"
                rows.append(display)
                if is_action_play_line(line, decoded):
                    action_rows.append(display)
                if len(rows) >= 240:
                    return rows, action_rows
    return rows, action_rows



def collect_method_candidates(cache_hits, binary_hits, log_hits):
    candidates = set()
    source_texts = []
    for hit in list(cache_hits) + list(binary_hits):
        candidates.update(hit.terms)
        source_texts.extend(hit.snippets)
    source_texts.extend(log_hits)
    for text in source_texts:
        candidates.update(METHOD_VALUE_RE.findall(text))
        candidates.update(METHOD_WORD_RE.findall(text))
        for word in PLAY_WORD_RE.findall(text):
            if is_interesting_method_word(word):
                candidates.add(word)
    priority = ("Stop", "Start", "Play", "Playback", "Preview", "Action", "Work", "Open", "nt", "gmbridge", "ngwebview")
    def sort_key(name):
        score = 0
        for idx, token in enumerate(priority):
            if token.lower() in name.lower():
                score -= 20 - idx
        return score, name.lower()
    return sorted(candidates, key=sort_key)


def is_interesting_method_word(word):
    if len(word) < 4 or len(word) > 96:
        return False
    lowered = word.lower()
    noisy = ("display", "autoplay", "openSSL".lower(), "openFile", "fopen", "opened", "opening", "close", "closed")
    if lowered in noisy:
        return False
    return any(token in lowered for token in ("play", "preview", "action", "work", "dance", "start", "stop", "open"))


def decode_videoinfo_from_line(line):
    match = re.search(r"/videoinfo\s+([A-Za-z0-9+/=]+)", line)
    if not match:
        return ""
    try:
        raw = base64.b64decode(match.group(1) + "===")
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return ""
    if isinstance(data, dict):
        return json.dumps(data, ensure_ascii=False)
    return str(data)


def is_action_play_line(line, decoded):
    text = f"{line} {decoded}"
    return any(token in text for token in ("l36-action", "action.fp.ps.netease.com", "l36.fp.ps.netease.com", "action_comment", "AssetsNotPatch/Action"))

def scan_unisdk_log(game_dir):
    path = game_dir / "nshm_Data" / "Plugins" / "x86_64" / "NtUniSdk.log"
    if not path.exists():
        return [], [], []
    rows = []
    qrcode_rows = []
    voice_rows = []
    patterns = (
        "methodId",
        "ntStartPlayback",
        "ntStopPlayback",
        "ntDownloadVoiceFile",
        "NgVoice_RAW",
        "CreateQRCode",
        "PresentQRCodeScanner",
        "QRCode file content",
        "presentQRCodeScanner success",
        "workId_",
    )
    try:
        text = path.read_text("utf-8", errors="ignore")
    except OSError:
        return [], [], []
    for line in text.splitlines():
        if not any(pattern in line for pattern in patterns):
            continue
        display = f"{path.name}: {line[:520]}"
        rows.append(display)
        if WORK_ID_RE.search(line):
            qrcode_rows.append(display)
        if any(token in line for token in ("ntStartPlayback", "ntStopPlayback", "ntDownloadVoiceFile", "NgVoice_RAW")):
            voice_rows.append(display)
    return rows[-240:], qrcode_rows[-160:], voice_rows[-120:]


def scan_text_file(path, root, terms, size=None):
    try:
        data = path.read_bytes()
    except OSError:
        return None
    text = data.decode("utf-8", errors="ignore")
    found = [term for term in terms if term in text]
    if not found:
        return None
    urls = [url for url in URL_RE.findall(text) if is_interesting_url(url)]
    snippets = []
    for term in found[:6]:
        idx = text.find(term)
        if idx >= 0:
            snippets.append(clean_snippet(text[max(0, idx - 220): idx + 520]))
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)
    return DiagnosticFileHit(rel, size if size is not None else len(data), found, sorted(set(urls))[:12], snippets)


def contains_term(data, term):
    raw = term.encode("utf-8")
    wide = term.encode("utf-16le")
    return raw in data or wide in data


def snippet_for_binary(data, term):
    for encoding in ("utf-8", "utf-16le"):
        needle = term.encode(encoding)
        idx = data.find(needle)
        if idx < 0:
            continue
        chunk = data[max(0, idx - 220): idx + 520]
        return clean_snippet(chunk.decode(encoding, errors="ignore"))
    return ""


def extract_urls(data):
    text = data.decode("utf-8", errors="ignore")
    return sorted(set(url for url in URL_RE.findall(text) if is_interesting_url(url)))[:12]


def is_interesting_url(url):
    return any(token in url for token in ("hapi.hi.163.com", "g.166.net", "netease", "action", "nshm", "leihuo", "l36-"))


def clean_snippet(text):
    text = text.replace("\x00", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:900]


def format_hit(hit):
    lines = [
        f"- {hit.path}",
        f"  size: {hit.size}",
        f"  terms: {', '.join(hit.terms[:30])}",
    ]
    for url in hit.urls[:6]:
        lines.append(f"  url: {url}")
    for snippet in hit.snippets[:3]:
        lines.append(f"  snippet: {snippet}")
    return lines


def pe_exports(path):
    data = Path(path).read_bytes()
    if len(data) < 0x40 or data[:2] != b"MZ":
        return []
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_offset:pe_offset + 4] != b"PE\0\0":
        return []
    number_of_sections = struct.unpack_from("<H", data, pe_offset + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe_offset + 20)[0]
    optional_offset = pe_offset + 24
    magic = struct.unpack_from("<H", data, optional_offset)[0]
    data_dir_offset = optional_offset + (112 if magic == 0x20B else 96)
    export_rva, _export_size = struct.unpack_from("<II", data, data_dir_offset)
    if not export_rva:
        return []
    section_offset = optional_offset + optional_size
    sections = []
    for idx in range(number_of_sections):
        offset = section_offset + idx * 40
        virtual_size, virtual_address, raw_size, raw_address = struct.unpack_from("<IIII", data, offset + 8)
        sections.append((virtual_address, virtual_size, raw_address, raw_size))
    export_offset = rva_to_offset(sections, export_rva)
    if export_offset is None:
        return []
    values = struct.unpack_from("<IIHHIIIIIII", data, export_offset)
    _flags, _time, _major, _minor, _name, _base, _func_count, name_count, _funcs, names_rva, _ords = values
    names_offset = rva_to_offset(sections, names_rva)
    if names_offset is None:
        return []
    exports = []
    for idx in range(name_count):
        name_rva = struct.unpack_from("<I", data, names_offset + idx * 4)[0]
        name_offset = rva_to_offset(sections, name_rva)
        if name_offset is None:
            continue
        end = data.find(b"\0", name_offset)
        if end > name_offset:
            exports.append(data[name_offset:end].decode("utf-8", errors="ignore"))
    return exports


def rva_to_offset(sections, rva):
    for virtual_address, virtual_size, raw_address, raw_size in sections:
        span = max(virtual_size, raw_size)
        if virtual_address <= rva < virtual_address + span:
            return raw_address + (rva - virtual_address)
    return None


def build_notes(report):
    notes = []
    all_binary_terms = {term for hit in report.binary_hits for term in hit.terms}
    all_cache_terms = {term for hit in report.cache_hits for term in hit.terms}
    if "unisdk_js_native_call" in all_binary_terms or "UniSDKJSBridge" in all_binary_terms:
        notes.append("已确认 UniSDK WebView bridge 存在，页面通过 methodId 调 native。")
    if "RegisterMethodIdList" in all_binary_terms:
        notes.append("已确认 native 层存在 RegisterMethodIdList，后续重点是找剧组站是否注册专属 methodId。")
    if {"CONTINUE_PLAY_LIST", "CONTINUE_PLAY_STATE"} & all_cache_terms:
        notes.append("缓存中发现连续播放状态，但更像大神站视频连续播放，不一定是游戏内剧组动作播放。")
    if any("Invoke cmd = Play" in line for line in report.log_hits):
        notes.append("日志发现 MLiveCCPlayerImpl Play，预览作品至少会触发 CDN 视频播放链路。")
    if report.action_play_logs:
        notes.append("发现疑似剧组/动作 CDN 播放日志，优先查看“剧组/动作播放日志”。")
    if report.qrcode_work_logs:
        notes.append("发现 workId_ 数字形式的二维码入口；这可能可用于绕过搜索，直接让游戏打开指定作品。")
    if report.voice_playback_logs:
        notes.append("ntStartPlayback/ntStopPlayback 已归因为 NgVoice 语音播放链路，不应直接当作剧组动作播放方法。")
    if "remote-debugging-port" not in all_binary_terms:
        notes.append("未发现明确 remote-debugging-port 线索，CEF DevTools 仍不作为优先路线。")
    if not any(term in set(report.method_candidates) for term in ("playWork", "previewWork", "openWork", "playAction")):
        notes.append("暂未发现明确 playWork/previewWork/openWork/playAction 方法；可继续关注 nt*/gmbridge*/execute_extend_func 的参数。")
    return notes


def main():
    report = run_stage_diagnostics()
    text = report.to_text()
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(text, "utf-8")
        print(f"诊断报告已写入：{sys.argv[1]}")
    else:
        print(text)


if __name__ == "__main__":
    main()
