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
