import os
import time
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

from automation import (
    click_xy,
    find_window,
    focus_window,
    get_process_integrity,
    hotkey,
    key_code_from_name,
    key_down,
    key_up,
    parse_key_combo,
    parse_key_duration,
    post_click_window_xy,
    post_click_xy,
    post_key,
    post_text,
    set_clipboard_text,
    window_to_screen_xy,
)
from models import ImageTarget, PointDef
from stage_transport import open_uri, send_http_request
from utils import parse_duration, render_template
from vision import MatchFailure, locate_template, locate_template_in_window


class DefaultWindowsBindings:
    click_xy = staticmethod(click_xy)
    find_window = staticmethod(find_window)
    focus_window = staticmethod(focus_window)
    hotkey = staticmethod(hotkey)
    key_down = staticmethod(key_down)
    key_up = staticmethod(key_up)
    post_click_window_xy = staticmethod(post_click_window_xy)
    post_click_xy = staticmethod(post_click_xy)
    post_key = staticmethod(post_key)
    post_text = staticmethod(post_text)
    set_clipboard_text = staticmethod(set_clipboard_text)
    window_to_screen_xy = staticmethod(window_to_screen_xy)
    locate_template = staticmethod(locate_template)
    locate_template_in_window = staticmethod(locate_template_in_window)
    open_uri = staticmethod(open_uri)
    send_http_request = staticmethod(send_http_request)


@dataclass(frozen=True)
class ExecutionSettings:
    window_hint: str
    focus_window: bool
    input_mode: str
    preview_clicks: bool
    points: Mapping[str, PointDef]
    image_targets: Mapping[str, ImageTarget]


@dataclass(frozen=True)
class WindowsExecutionContext:
    settings: ExecutionSettings
    window: Mapping[str, Any] | None
    message_hwnd: int | None


def parse_execution_settings(document, base_dir=None):
    data = document if isinstance(document, dict) else {}
    groups = data.get("point_groups") or []
    active_name = str(data.get("active_point_group", "")).strip()
    selected_group = next(
        (group for group in groups if str(group.get("name", "")).strip() == active_name),
        groups[0] if groups else None,
    )
    raw_points = selected_group.get("points", []) if selected_group else data.get("points", [])
    points = {}
    for item in raw_points or []:
        name = str(item.get("name", "")).strip()
        if name:
            points[name] = PointDef(name=name, x=int(item.get("x", 0)), y=int(item.get("y", 0)))

    image_targets = {}
    for item in data.get("image_targets", []) or []:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        template_path = str(item.get("template_path", "")).strip()
        mask_path = str(item.get("mask_path", "")).strip()
        if template_path and base_dir and not os.path.isabs(template_path):
            template_path = os.path.abspath(os.path.join(base_dir, template_path))
        if mask_path and base_dir and not os.path.isabs(mask_path):
            mask_path = os.path.abspath(os.path.join(base_dir, mask_path))
        image_targets[name] = ImageTarget(
            name=name,
            template_path=template_path,
            match_mode=str(item.get("match_mode", "grayscale")),
            mask_path=mask_path,
            edge_low=int(item.get("edge_low", 60)),
            edge_high=int(item.get("edge_high", 160)),
            region=str(item.get("region", "")),
            threshold=float(item.get("threshold", 0.85)),
            offset_x=int(item.get("offset_x", 0)),
            offset_y=int(item.get("offset_y", 0)),
            retry_seconds=max(0.0, float(item.get("retry_seconds", 3.0))),
            retry_attempts=max(1, int(item.get("retry_attempts", 5))),
            retry_interval=max(0.0, float(item.get("retry_interval", 0.25))),
        )

    input_mode = str(data.get("input_mode", "foreground")).strip()
    if input_mode not in {"foreground", "window_message"}:
        input_mode = "foreground"
    return ExecutionSettings(
        window_hint=str(data.get("window_hint", "")).strip(),
        focus_window=bool(data.get("focus_window", True)),
        input_mode=input_mode,
        preview_clicks=bool(data.get("preview_clicks", False)),
        points=points,
        image_targets=image_targets,
    )


class WindowsActionExecutor:
    def __init__(
        self,
        control,
        config_provider: Callable[[], Mapping[str, Any]],
        base_dir=None,
        emit_log: Callable[[str], None] | None = None,
        bindings=None,
        point_visualizer=None,
        integrity_reader=get_process_integrity,
    ):
        self.control = control
        self.config_provider = config_provider
        self.base_dir = base_dir
        self.emit_log = emit_log or (lambda _message: None)
        self.bindings = bindings or DefaultWindowsBindings()
        self.point_visualizer = point_visualizer
        self.integrity_reader = integrity_reader
        self._held_keys = set()

    def prepare_job(self, _job, prepared):
        settings = parse_execution_settings(self.config_provider(), self.base_dir)
        needs_window = settings.focus_window or settings.input_mode == "window_message"
        window = self.bindings.find_window(settings.window_hint) if needs_window else None
        if needs_window and not window:
            raise RuntimeError(f"找不到目标窗口：{settings.window_hint or '未设置窗口关键词'}")
        if window and int(window.get("pid", 0)):
            target_integrity = self.integrity_reader(int(window["pid"]))
            app_integrity = self.integrity_reader(os.getpid())
            if (
                target_integrity.get("known")
                and app_integrity.get("known")
                and int(target_integrity.get("rid", 0)) > int(app_integrity.get("rid", 0))
            ):
                raise RuntimeError(
                    "输入权限不足：目标游戏以管理员权限运行，Macro Studio 当前为普通权限。"
                    "请关闭当前程序后使用 npm run dev:admin 启动。"
                )
        if window and settings.focus_window:
            self.bindings.focus_window(window["hwnd"])
        message_hwnd = int(window["hwnd"]) if window and settings.input_mode == "window_message" else None
        return replace(
            prepared,
            context=WindowsExecutionContext(
                settings=settings,
                window=window,
                message_hwnd=message_hwnd,
            ),
        )

    def execute_step(self, step, job, prepared):
        context = prepared.context
        if not isinstance(context, WindowsExecutionContext):
            raise RuntimeError("真实执行上下文未准备")
        song = job.song
        kind = step.kind
        value = render_template(step.value, song)

        if kind == "click":
            self._click_point(step.target, context)
        elif kind == "image_click":
            self._click_image(value, context, getattr(step, "verify_target", ""))
        elif kind == "paste":
            self._paste(value or getattr(song, "keyword", "") or getattr(song, "title", ""), context)
        elif kind == "wait":
            seconds = parse_duration(value)
            self._log(f"等待 {seconds:g} 秒")
            self.control.wait(seconds)
        elif kind == "enter":
            self._press_keys([key_code_from_name("enter")], 0.025, context)
            self._log("按 Enter")
        elif kind == "ctrl_a":
            self._press_keys(
                [key_code_from_name("ctrl"), key_code_from_name("a")],
                0.025,
                context,
            )
            self._log("按 Ctrl+A")
        elif kind == "key":
            key_name = value.strip()
            self._press_keys([key_code_from_name(key_name)], 0.025, context)
            self._log(f"按键：{key_name}")
        elif kind == "key_hold":
            key_name, seconds = parse_key_duration(value, 0.5)
            self._press_keys([key_code_from_name(key_name)], seconds, context)
            self._log(f"长按：{key_name} {seconds:.2f}s")
        elif kind == "key_down":
            key_name = value.strip()
            vk = key_code_from_name(key_name)
            self._set_key(context, vk, True)
            self._held_keys.add((context.message_hwnd, vk))
            self._log(f"按下：{key_name}")
        elif kind == "key_up":
            key_name = value.strip()
            vk = key_code_from_name(key_name)
            self._set_key(context, vk, False)
            self._held_keys.discard((context.message_hwnd, vk))
            self._log(f"抬起：{key_name}")
        elif kind in {"hotkey", "hotkey_hold"}:
            key_text, seconds = (
                parse_key_duration(value, 0.5) if kind == "hotkey_hold" else (value, 0.025)
            )
            names = parse_key_combo(key_text)
            self._press_keys([key_code_from_name(name) for name in names], seconds, context)
            label = "组合键长按" if kind == "hotkey_hold" else "快捷键"
            self._log(f"{label}：{'+'.join(names)}")
        elif kind == "open_uri":
            self.bindings.open_uri(value)
            self._log("已打开链接或协议")
        elif kind == "http_request":
            status, _body = self.bindings.send_http_request(value)
            self._log(f"HTTP 请求完成：{status}")
        elif kind == "log":
            self._log(value)
        else:
            raise RuntimeError(f"未知动作类型：{kind}")

        wait_after = render_template(step.wait_after, song).strip()
        if kind != "wait" and wait_after and not self.control.should_stop():
            seconds = parse_duration(wait_after)
            self._log(f"动作后等待 {seconds:g} 秒")
            if self.control.wait(seconds):
                self._log("动作后等待完成")
        if not self.control.should_stop():
            self.control.wait(0.18 if context.message_hwnd else 0.08)

    def cleanup(self):
        held_keys = list(self._held_keys)
        self._held_keys.clear()
        for message_hwnd, vk in reversed(held_keys):
            try:
                if message_hwnd:
                    self.bindings.post_key(message_hwnd, vk, False)
                else:
                    self.bindings.key_up(vk)
            except Exception:
                pass

    def _click_point(self, name, context):
        point = context.settings.points.get(name)
        if not point:
            raise RuntimeError(f"点位不存在：{name}")
        if point.x == 0 and point.y == 0:
            raise RuntimeError(f"点位未采集：{name}")
        self._click(context, point.x, point.y)
        self._preview_click(name, point.x, point.y, context, window_relative=False)
        self._log(f"点击点位：{name}，坐标 {point.x}, {point.y}")

    def _click_image(self, name, context, verify_target_name=""):
        target = self._image_target(name, context)
        match = self._locate_image_target(target, context, "点击目标")
        if match is None or self.control.should_stop():
            return

        click_x = match.x + target.offset_x
        click_y = match.y + target.offset_y
        self._log(
            f"图像已命中：{target.name} ({match.score:.3f})，准备点击 {click_x}, {click_y}"
        )
        try:
            if context.message_hwnd:
                self.bindings.post_click_window_xy(context.message_hwnd, click_x, click_y)
            else:
                self._click(context, click_x, click_y)
        except Exception as exc:
            raise RuntimeError(
                f"图像已命中但点击失败：{target.name} ({match.score:.3f})，坐标 {click_x}, {click_y}；{exc}"
            ) from exc
        self._preview_click(
            target.name,
            click_x,
            click_y,
            context,
            window_relative=bool(context.message_hwnd),
        )
        self._log(
            f"图像命中并点击：{target.name} ({match.score:.3f})，坐标 {click_x}, {click_y}"
        )

        verify_name = str(verify_target_name or "").strip()
        if verify_name and not self.control.should_stop():
            verify_target = self._image_target(verify_name, context)
            self._log(f"开始点击后验证：等待图像目标「{verify_target.name}」出现")
            verified = self._locate_image_target(verify_target, context, "点击后验证")
            if verified is not None and not self.control.should_stop():
                self._log(
                    f"点击后验证通过：{verify_target.name} ({verified.score:.3f})，"
                    f"坐标 {verified.x}, {verified.y}"
                )

    @staticmethod
    def _image_target(name, context):
        target_name = str(name or "").strip()
        target = context.settings.image_targets.get(target_name)
        if target:
            return target
        available = "、".join(context.settings.image_targets) or "暂无图像目标"
        raise RuntimeError(f"图像目标不存在：{target_name or '未填写'}。当前可用：{available}")

    def _locate_image_target(self, target, context, purpose):
        retry_seconds = max(0.0, float(target.retry_seconds))
        retry_attempts = max(1, int(target.retry_attempts))
        retry_interval = max(0.0, float(target.retry_interval))
        region_label = target.region or "全窗口"
        source_label = "后台窗口" if context.message_hwnd else "屏幕"
        self._log(
            f"{purpose}识别：{target.name}；来源 {source_label}；模式 {target.match_mode}；"
            f"阈值 {target.threshold:.3f}；范围 {region_label}；最多 {retry_attempts} 次；"
            f"间隔 {retry_interval:.2f} 秒；最长 {retry_seconds:.1f} 秒"
        )
        started_at = time.monotonic()
        deadline = started_at + retry_seconds
        attempts = 0
        best_score = None
        last_error = None

        while attempts < retry_attempts and not self.control.should_stop():
            attempts += 1
            try:
                if context.message_hwnd:
                    match = self.bindings.locate_template_in_window(
                        target.template_path,
                        context.message_hwnd,
                        target.region,
                        target.threshold,
                        target.match_mode,
                        target.mask_path,
                        target.edge_low,
                        target.edge_high,
                    )
                else:
                    match = self.bindings.locate_template(
                        target.template_path,
                        target.region,
                        target.threshold,
                        target.match_mode,
                        target.mask_path,
                        target.edge_low,
                        target.edge_high,
                    )
                elapsed = max(0.0, time.monotonic() - started_at)
                self._log(
                    f"{purpose}识别命中：{target.name}；第 {attempts}/{retry_attempts} 次；"
                    f"相似度 {match.score:.3f} / 阈值 {target.threshold:.3f}；耗时 {elapsed:.2f} 秒"
                )
                return match
            except Exception as exc:
                last_error = exc
                now = time.monotonic()
                elapsed = max(0.0, now - started_at)
                result = exc.result if isinstance(exc, MatchFailure) else None
                if result is not None:
                    score = float(result.score)
                    best_score = score if best_score is None else max(best_score, score)
                    self._log(
                        f"{purpose}识别尝试 {attempts}/{retry_attempts} 未命中：{target.name}；"
                        f"相似度 {score:.3f} / 阈值 {target.threshold:.3f}；耗时 {elapsed:.2f} 秒"
                    )
                else:
                    self._log(
                        f"{purpose}识别尝试 {attempts}/{retry_attempts} 失败：{target.name}；"
                        f"{exc}；耗时 {elapsed:.2f} 秒"
                    )

                attempts_exhausted = attempts >= retry_attempts
                time_exhausted = retry_seconds <= 0 or now >= deadline
                if attempts_exhausted or time_exhausted:
                    reason = "达到最多尝试次数" if attempts_exhausted else "达到最长重试时长"
                    score_summary = (
                        f"；本轮最高相似度 {best_score:.3f} / 阈值 {target.threshold:.3f}"
                        if best_score is not None
                        else ""
                    )
                    raise RuntimeError(
                        f"{purpose}识别失败：{target.name}；实际尝试 {attempts}/{retry_attempts} 次；"
                        f"实际耗时 {elapsed:.2f} 秒；{reason}{score_summary}；最后错误：{exc}"
                    ) from exc

                remaining = max(0.0, deadline - now)
                wait_seconds = min(retry_interval, remaining)
                if wait_seconds > 0 and not self.control.wait(wait_seconds):
                    return None

        if self.control.should_stop():
            return None
        raise RuntimeError(
            f"{purpose}识别失败：{target.name}；实际尝试 {attempts}/{retry_attempts} 次；"
            f"最后错误：{last_error or '未知错误'}"
        )
    def _preview_click(self, name, x, y, context, window_relative):
        if not context.settings.preview_clicks or self.point_visualizer is None:
            return
        try:
            screen_x, screen_y = int(x), int(y)
            if window_relative and context.message_hwnd:
                screen_x, screen_y = self.bindings.window_to_screen_xy(
                    context.message_hwnd,
                    screen_x,
                    screen_y,
                )
            self.point_visualizer(f"执行点击 · {name}", screen_x, screen_y, 0.85)
        except Exception as exc:
            self._log(f"点击位置预览失败：{exc}")

    def _paste(self, value, context):
        text = str(value)
        if context.message_hwnd:
            self.bindings.post_text(context.message_hwnd, text)
        else:
            self.bindings.set_clipboard_text(text)
            if self.control.wait(0.12):
                self.bindings.hotkey(["ctrl", "v"])
        self._log(f"粘贴文本：{len(text)} 字符")

    def _click(self, context, x, y):
        if context.message_hwnd:
            self.bindings.post_click_xy(context.message_hwnd, int(x), int(y))
        else:
            self.bindings.click_xy(int(x), int(y))

    def _press_keys(self, codes, seconds, context):
        pressed = []
        try:
            for vk in codes:
                self._set_key(context, vk, True)
                pressed.append(vk)
                if not self.control.wait(0.015):
                    break
            if pressed and not self.control.should_stop():
                self.control.wait(seconds)
        finally:
            for vk in reversed(pressed):
                self._set_key(context, vk, False)
                self.control.wait(0.015)

    def _set_key(self, context, vk, is_down):
        if context.message_hwnd:
            self.bindings.post_key(context.message_hwnd, vk, is_down)
        elif is_down:
            self.bindings.key_down(vk)
        else:
            self.bindings.key_up(vk)

    def _log(self, message):
        self.emit_log(str(message))
