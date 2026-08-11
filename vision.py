import os
from dataclasses import dataclass


class VisionUnavailable(RuntimeError):
    pass


@dataclass
class MatchResult:
    x: int
    y: int
    score: float
    width: int
    height: int


def parse_region(text):
    value = (text or "").strip()
    if not value:
        return None
    parts = [part.strip() for part in value.replace("，", ",").split(",")]
    if len(parts) != 4:
        raise ValueError("识别区域格式应为 x,y,w,h，例如 100,200,400,300。")
    try:
        x, y, w, h = [int(float(part)) for part in parts]
    except ValueError as exc:
        raise ValueError("识别区域只能填写数字，格式为 x,y,w,h。") from exc
    if w <= 0 or h <= 0:
        raise ValueError("识别区域的宽高必须大于 0。")
    return x, y, w, h


def locate_template(template_path, region_text="", threshold=0.85):
    try:
        import cv2
        import numpy as np
        from PIL import Image, ImageGrab
    except Exception as exc:
        raise VisionUnavailable("image_click 需要 pillow、opencv-python、numpy。请先安装这些依赖。") from exc

    path = os.path.abspath(os.path.expanduser(template_path or ""))
    if not os.path.exists(path):
        raise FileNotFoundError(f"模板图不存在：{path}")

    region = parse_region(region_text)
    bbox = None
    offset_x = 0
    offset_y = 0
    if region:
        offset_x, offset_y, w, h = region
        bbox = (offset_x, offset_y, offset_x + w, offset_y + h)

    screenshot = ImageGrab.grab(bbox=bbox)
    crop_left = crop_top = 0
    region = parse_region(region_text)
    if region:
        region_x, region_y, region_w, region_h = region
        crop_left = max(0, region_x - offset_x)
        crop_top = max(0, region_y - offset_y)
        crop_right = min(screenshot.width, region_x + region_w - offset_x)
        crop_bottom = min(screenshot.height, region_y + region_h - offset_y)
        if crop_right <= crop_left or crop_bottom <= crop_top:
            raise RuntimeError("识别区域不在目标窗口范围内。")
        screenshot = screenshot.crop((crop_left, crop_top, crop_right, crop_bottom))
    screen_rgb = np.array(screenshot.convert("RGB"))
    template_rgb = np.array(Image.open(path).convert("RGB"))
    if template_rgb.shape[0] > screen_rgb.shape[0] or template_rgb.shape[1] > screen_rgb.shape[1]:
        raise RuntimeError("模板图比识别区域更大，无法匹配。")

    screen_gray = cv2.cvtColor(screen_rgb, cv2.COLOR_RGB2GRAY)
    template_gray = cv2.cvtColor(template_rgb, cv2.COLOR_RGB2GRAY)
    result = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    _min_val, max_val, _min_loc, max_loc = cv2.minMaxLoc(result)
    score = float(max_val)
    tw = int(template_gray.shape[1])
    th = int(template_gray.shape[0])
    center_x = int(offset_x + max_loc[0] + tw / 2)
    center_y = int(offset_y + max_loc[1] + th / 2)
    if score < float(threshold):
        raise RuntimeError(f"未达到识别阈值：最高相似度 {score:.3f}，阈值 {float(threshold):.3f}")
    return MatchResult(x=center_x, y=center_y, score=score, width=tw, height=th)
def locate_template_in_window(template_path, hwnd, region_text="", threshold=0.85):
    """Capture an occluded window through Windows Graphics Capture."""
    try:
        import ctypes
        from ctypes import wintypes
        import threading
        import cv2
        import numpy as np
        from PIL import Image
        from windows_capture import WindowsCapture
    except Exception as exc:
        raise VisionUnavailable("后台图像识别需要 windows-capture、pillow、opencv-python、numpy。") from exc
    path = os.path.abspath(os.path.expanduser(template_path or ""))
    if not os.path.exists(path):
        raise FileNotFoundError(f"模板图不存在：{path}")
    done, holder = threading.Event(), {}
    capture = WindowsCapture(cursor_capture=False, draw_border=False, window_hwnd=int(hwnd), minimum_update_interval=0)
    @capture.event
    def on_frame_arrived(frame, control):
        holder["frame"] = frame.frame_buffer.copy()
        control.stop(); done.set()
    @capture.event
    def on_closed():
        holder["error"] = "Windows Graphics Capture 已关闭"
        done.set()
    control = capture.start_free_threaded()
    if not done.wait(8):
        control.stop()
        raise RuntimeError("等待后台窗口截图超时。")
    if "error" in holder or "frame" not in holder:
        raise RuntimeError(holder.get("error", "未收到后台窗口截图。"))
    rect = wintypes.RECT(); ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    window_w, window_h = rect.right - rect.left, rect.bottom - rect.top
    frame = holder["frame"][:, :, :3]
    frame_h, frame_w = frame.shape[:2]
    scale_x, scale_y = frame_w / window_w, frame_h / window_h
    left = top = 0
    region = parse_region(region_text)
    if region:
        x, y, width, height = region
        left = max(0, int((x - rect.left) * scale_x)); top = max(0, int((y - rect.top) * scale_y))
        right = min(frame_w, int((x + width - rect.left) * scale_x)); bottom = min(frame_h, int((y + height - rect.top) * scale_y))
        if right <= left or bottom <= top: raise RuntimeError("识别区域不在目标窗口范围内。")
        frame = frame[top:bottom, left:right]
    template = np.array(Image.open(path).convert("RGB"))
    if template.shape[0] > frame.shape[0] or template.shape[1] > frame.shape[1]: raise RuntimeError("模板图比识别区域更大，无法匹配。")
    result = cv2.matchTemplate(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.cvtColor(template, cv2.COLOR_RGB2GRAY), cv2.TM_CCOEFF_NORMED)
    _a, score, _b, loc = cv2.minMaxLoc(result)
    if score < float(threshold): raise RuntimeError(f"后台截图未达到识别阈值：最高相似度 {score:.3f}，阈值 {float(threshold):.3f}")
    height, width = template.shape[:2]
    return MatchResult(x=int(rect.left + (left + loc[0] + width / 2) / scale_x), y=int(rect.top + (top + loc[1] + height / 2) / scale_y), score=float(score), width=width, height=height)
