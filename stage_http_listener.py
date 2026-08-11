import argparse
import ctypes
import json
import os
import re
import sys
import subprocess
import threading
import time
import urllib.parse


TARGET_HOST = "hapi.hi.163.com"
TARGET_PATH = "/nshm/action-station/work/list/search"
CAPTURE_KEYS = (
    "role_id",
    "user_id",
    "sort",
    "page_size",
    "contents",
    "sub_types",
    "actor_count_contents",
)
MAX_STREAM_BYTES = 256 * 1024


class StageCaptureError(RuntimeError):
    pass


class TcpStreamBuffer:
    def __init__(self):
        self.segments = {}

    def add(self, sequence, payload):
        if payload:
            self.segments.setdefault(int(sequence), bytes(payload))

    def joined(self):
        if not self.segments:
            return b""
        chunks = []
        end = None
        total = 0
        for sequence, payload in sorted(self.segments.items()):
            if end is None:
                chunks.append(payload)
                end = sequence + len(payload)
            elif sequence <= end:
                overlap = end - sequence
                if overlap < len(payload):
                    chunks.append(payload[overlap:])
                    end += len(payload) - overlap
            else:
                break
            total += len(payload)
            if total >= MAX_STREAM_BYTES:
                break
        return b"".join(chunks)[-MAX_STREAM_BYTES:]


def parse_http_requests(data):
    results = []
    pattern = br"(?:^|\r\n)(GET|POST)\s+([^\s]+)\s+HTTP/1\.[01]\r\n"
    for match in re.finditer(pattern, data):
        header_end = data.find(b"\r\n\r\n", match.end())
        if header_end < 0:
            continue
        request_line_end = data.find(b"\r\n", match.start())
        if request_line_end < 0:
            continue
        header_blob = data[request_line_end + 2:header_end]
        headers = {}
        for raw_line in header_blob.split(b"\r\n"):
            if b":" not in raw_line:
                continue
            name, value = raw_line.split(b":", 1)
            headers[name.decode("latin-1").strip().lower()] = value.decode("latin-1").strip()
        results.append((match.group(2).decode("latin-1"), headers))
    return results


def config_from_http_request(target, headers):
    if target.startswith("http://") or target.startswith("https://"):
        parsed = urllib.parse.urlsplit(target)
        host = parsed.netloc.split(":", 1)[0].lower()
    else:
        host = headers.get("host", "").split(":", 1)[0].lower()
        parsed = urllib.parse.urlsplit("http://" + host + target)
    if host != TARGET_HOST or parsed.path != TARGET_PATH:
        return None
    params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    skey = headers.get("skey", "").strip()
    if not skey:
        return None
    result = {
        "base_url": f"http://{TARGET_HOST}{TARGET_PATH}",
        "skey": skey,
    }
    for key in CAPTURE_KEYS:
        if key in params:
            result[key] = params[key][0]
    if params.get("keyword"):
        result["keyword"] = params["keyword"][0]
    return result


def extract_stage_config(data):
    for target, headers in parse_http_requests(data):
        config = config_from_http_request(target, headers)
        if config:
            return config
    return None


def capture_once(timeout=90):
    try:
        import pydivert
    except ImportError as exc:
        raise StageCaptureError("缺少 pydivert，请先运行 pip install pydivert") from exc
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise StageCaptureError("监听游戏网络请求需要管理员权限")

    streams = {}
    handle_box = {}

    def close_after_timeout():
        time.sleep(max(1, timeout))
        handle = handle_box.get("handle")
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass

    threading.Thread(target=close_after_timeout, daemon=True).start()
    packet_filter = "outbound and tcp.DstPort == 80 and tcp.PayloadLength > 0"
    started = time.monotonic()
    try:
        with pydivert.WinDivert(packet_filter, flags=pydivert.Flag.SNIFF) as handle:
            handle_box["handle"] = handle
            for packet in handle:
                if time.monotonic() - started >= timeout:
                    break
                payload = packet.payload
                if not payload or packet.tcp is None:
                    continue
                flow = (packet.src_addr, packet.src_port, packet.dst_addr, packet.dst_port)
                stream = streams.setdefault(flow, TcpStreamBuffer())
                stream.add(packet.tcp.seq_num, payload)
                config = extract_stage_config(stream.joined())
                if config:
                    return config
    except OSError as exc:
        if time.monotonic() - started < timeout - 1:
            raise StageCaptureError(f"WinDivert 启动失败：{exc}") from exc
    finally:
        handle_box["handle"] = None
    raise StageCaptureError("监听超时，请确认游戏内执行了一次剧组站作品搜索")


def write_result(path, payload):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False)
    os.replace(temp_path, path)


def launch_elevated_capture(output_path, timeout=90):
    script_path = os.path.abspath(__file__)
    params = subprocess.list2cmdline(
        [script_path, "--output", output_path, "--timeout", str(int(timeout))]
    )
    shell_execute = ctypes.windll.shell32.ShellExecuteW
    shell_execute.restype = ctypes.c_void_p
    result = shell_execute(
        None,
        "runas",
        sys.executable,
        params,
        os.path.dirname(script_path),
        0,
    )
    if not result or result <= 32:
        raise StageCaptureError("管理员监听进程未能启动，可能取消了 UAC 授权")

def main():
    parser = argparse.ArgumentParser(description="Capture one Macro Studio stage-search HTTP request.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    try:
        write_result(args.output, {"ok": True, "config": capture_once(args.timeout)})
        return 0
    except Exception as exc:
        write_result(args.output, {"ok": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
