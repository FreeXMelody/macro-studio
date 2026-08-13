import base64
import io
import os
from dataclasses import dataclass


MATCH_MODES = {"smart", "grayscale", "edge", "masked", "masked_edge"}


class VisionUnavailable(RuntimeError):
    pass


class MatchFailure(RuntimeError):
    def __init__(self, message, result=None):
        super().__init__(message)
        self.result = result


@dataclass
class MatchResult:
    x: int
    y: int
    score: float
    width: int
    height: int
    match_mode: str = "grayscale"
    preview_data_url: str = ""
    search_x: int = 0
    search_y: int = 0
    search_width: int = 0
    search_height: int = 0
    capture_width: int = 0
    capture_height: int = 0


def parse_region(text):
    value = (text or "").strip()
    if not value:
        return None
    parts = [part.strip() for part in value.replace("，", ",").split(",")]
    if len(parts) != 4:
        raise ValueError("识别区域格式应为 x,y,w,h，例如 100,200,400,300。")
    try:
        x, y, width, height = [int(float(part)) for part in parts]
    except ValueError as exc:
        raise ValueError("识别区域只能填写数字，格式为 x,y,w,h。") from exc
    if width <= 0 or height <= 0:
        raise ValueError("识别区域的宽高必须大于 0。")
    return x, y, width, height


def locate_template(
    template_path,
    region_text="",
    threshold=0.85,
    match_mode="grayscale",
    mask_path="",
    edge_low=60,
    edge_high=160,
):
    """Find a template on the desktop and return screen coordinates."""
    try:
        import cv2
        import numpy as np
        from PIL import Image, ImageGrab
    except Exception as exc:
        raise VisionUnavailable("image_click 需要 pillow、opencv-python、numpy。请先安装这些依赖。") from exc

    path = _image_path(template_path, "模板图")
    region = parse_region(region_text)
    offset_x = region[0] if region else 0
    offset_y = region[1] if region else 0
    bbox = None
    if region:
        x, y, width, height = region
        bbox = (x, y, x + width, y + height)

    screenshot = ImageGrab.grab(bbox=bbox)
    image_rgb = np.array(screenshot.convert("RGB"))
    result = _match_template_image(
        cv2,
        np,
        Image,
        image_rgb,
        path,
        threshold,
        match_mode,
        mask_path,
        edge_low,
        edge_high,
        source_label="",
    )
    result.x += offset_x
    result.y += offset_y
    result.search_x = offset_x
    result.search_y = offset_y
    result.search_width = int(image_rgb.shape[1])
    result.search_height = int(image_rgb.shape[0])
    result.capture_width = int(image_rgb.shape[1])
    result.capture_height = int(image_rgb.shape[0])
    return result


def locate_template_in_window(
    template_path,
    hwnd,
    region_text="",
    threshold=0.85,
    match_mode="grayscale",
    mask_path="",
    edge_low=60,
    edge_high=160,
):
    """Find a template with Windows Graphics Capture and return window-relative coordinates."""
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

    path = _image_path(template_path, "模板图")
    done = threading.Event()
    holder = {}
    capture = WindowsCapture(
        cursor_capture=False,
        draw_border=False,
        window_hwnd=int(hwnd),
        minimum_update_interval=0,
    )

    @capture.event
    def on_frame_arrived(frame, control):
        holder["frame"] = frame.frame_buffer.copy()
        control.stop()
        done.set()

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

    window_rect = wintypes.RECT()
    capture_rect = wintypes.RECT()
    user32 = ctypes.windll.user32
    if not user32.GetWindowRect(int(hwnd), ctypes.byref(window_rect)):
        raise RuntimeError("无法读取目标窗口尺寸。")
    capture_rect.left = window_rect.left
    capture_rect.top = window_rect.top
    capture_rect.right = window_rect.right
    capture_rect.bottom = window_rect.bottom
    try:
        # Windows Graphics Capture uses the visible DWM frame, excluding invisible
        # resize borders. Mapping against this rectangle keeps WGC and Win32 in the
        # same physical-pixel coordinate system at non-100% display scaling.
        dwmapi = ctypes.windll.dwmapi
        if dwmapi.DwmGetWindowAttribute(
            int(hwnd),
            9,  # DWMWA_EXTENDED_FRAME_BOUNDS
            ctypes.byref(capture_rect),
            ctypes.sizeof(capture_rect),
        ) != 0:
            raise RuntimeError
    except Exception:
        capture_rect.left = window_rect.left
        capture_rect.top = window_rect.top
        capture_rect.right = window_rect.right
        capture_rect.bottom = window_rect.bottom

    capture_width = capture_rect.right - capture_rect.left
    capture_height = capture_rect.bottom - capture_rect.top
    if capture_width <= 0 or capture_height <= 0:
        raise RuntimeError("目标窗口捕获边界无效。")

    full_frame_bgr = holder["frame"][:, :, :3]
    frame_height, frame_width = full_frame_bgr.shape[:2]
    scale_x = frame_width / capture_width
    scale_y = frame_height / capture_height
    capture_offset_x = capture_rect.left - window_rect.left
    capture_offset_y = capture_rect.top - window_rect.top
    crop_left = 0
    crop_top = 0
    crop_right = frame_width
    crop_bottom = frame_height
    region = parse_region(region_text)
    if region:
        x, y, width, height = region
        capture_x = x - capture_offset_x
        capture_y = y - capture_offset_y
        crop_left = max(0, int(capture_x * scale_x))
        crop_top = max(0, int(capture_y * scale_y))
        crop_right = min(frame_width, int((capture_x + width) * scale_x))
        crop_bottom = min(frame_height, int((capture_y + height) * scale_y))
        if crop_right <= crop_left or crop_bottom <= crop_top:
            raise RuntimeError("识别区域不在目标窗口捕获范围内。")
    frame_bgr = full_frame_bgr[crop_top:crop_bottom, crop_left:crop_right]
    image_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    full_image_rgb = cv2.cvtColor(full_frame_bgr, cv2.COLOR_BGR2RGB)

    def enrich_result(match):
        candidate_center = (crop_left + match.x, crop_top + match.y)
        match.preview_data_url = _annotated_window_preview(
            Image,
            full_image_rgb,
            (crop_left, crop_top, crop_right, crop_bottom),
            candidate_center,
            (match.width, match.height),
            match.score,
            match.match_mode,
        )
        match.search_x = capture_offset_x + int(crop_left / scale_x)
        match.search_y = capture_offset_y + int(crop_top / scale_y)
        match.search_width = max(1, int((crop_right - crop_left) / scale_x))
        match.search_height = max(1, int((crop_bottom - crop_top) / scale_y))
        match.capture_width = int(frame_width)
        match.capture_height = int(frame_height)
        match.x = capture_offset_x + int((crop_left + match.x) / scale_x)
        match.y = capture_offset_y + int((crop_top + match.y) / scale_y)
        match.width = max(1, int(match.width / scale_x))
        match.height = max(1, int(match.height / scale_y))
        return match

    try:
        result = _match_template_image(
            cv2,
            np,
            Image,
            image_rgb,
            path,
            threshold,
            match_mode,
            mask_path,
            edge_low,
            edge_high,
            source_label="后台截图",
        )
    except MatchFailure as exc:
        if exc.result:
            enrich_result(exc.result)
        raise

    return enrich_result(result)

def _match_template_image(
    cv2,
    np,
    Image,
    image_rgb,
    template_path,
    threshold,
    requested_mode,
    mask_path,
    edge_low,
    edge_high,
    source_label,
):
    template_image = Image.open(template_path).convert("RGBA")
    template_rgba = np.array(template_image)
    template_rgb = template_rgba[:, :, :3]
    mask = _load_mask(np, Image, mask_path, template_rgba[:, :, 3], template_image.size)
    mode = _resolve_mode(requested_mode, mask)
    if mode in {"masked", "masked_edge"} and mask is None:
        raise ValueError("当前匹配方式需要先绘制并保存有效区域遮罩。")
    if template_rgb.shape[0] > image_rgb.shape[0] or template_rgb.shape[1] > image_rgb.shape[1]:
        raise RuntimeError("模板图比识别区域更大，无法匹配。")

    image_gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    template_gray = cv2.cvtColor(template_rgb, cv2.COLOR_RGB2GRAY)
    edge_low = max(0, min(255, int(edge_low)))
    edge_high = max(edge_low + 1, min(255, int(edge_high)))

    uses_edges = mode in {"edge", "masked_edge"}
    template_edges = None
    if uses_edges:
        image_edges = cv2.Canny(
            cv2.GaussianBlur(image_gray, (5, 5), 0),
            edge_low,
            edge_high,
            L2gradient=True,
        )
        template_edges = cv2.Canny(
            cv2.GaussianBlur(template_gray, (5, 5), 0),
            edge_low,
            edge_high,
            L2gradient=True,
        )
        if not np.any(template_edges):
            raise ValueError("模板没有可用于边缘匹配的轮廓，请降低边缘阈值或改用灰度匹配。")
        # A small soft edge band tolerates anti-aliasing and one-pixel rendering shifts.
        image_input = cv2.GaussianBlur(image_edges, (3, 3), 0)
        template_input = cv2.GaussianBlur(template_edges, (3, 3), 0)
    else:
        image_input = image_gray
        template_input = template_gray

    uses_mask = mode in {"masked", "masked_edge"}
    if mode == "masked_edge":
        # Only template contour neighbourhoods carry edge evidence. Keeping flat or
        # changing scene pixels in the user mask must not dilute the correlation.
        edge_support = cv2.dilate(
            np.where(template_edges > 0, 255, 0).astype("uint8"),
            np.ones((5, 5), dtype="uint8"),
            iterations=1,
        )
        mask = cv2.bitwise_and(mask, edge_support)
        if cv2.countNonZero(mask) < 8:
            raise ValueError("有效区域没有覆盖足够的模板轮廓，请保留图标边缘后重试。")
    uses_difference = mode == "masked"
    method = (
        cv2.TM_SQDIFF_NORMED
        if uses_difference
        else cv2.TM_CCORR_NORMED
        if uses_mask or uses_edges
        else cv2.TM_CCOEFF_NORMED
    )
    if uses_mask:
        match_map = cv2.matchTemplate(image_input, template_input, method, mask=mask)
    else:
        match_map = cv2.matchTemplate(image_input, template_input, method)
    fill = 1.0 if uses_difference else -1.0
    match_map = np.nan_to_num(match_map, nan=fill, posinf=fill, neginf=fill)
    minimum, maximum, minimum_location, maximum_location = cv2.minMaxLoc(match_map)
    if uses_difference:
        score = float(1.0 - max(0.0, min(1.0, minimum)))
        location = minimum_location
    else:
        score = float(maximum)
        location = maximum_location
    height, width = template_gray.shape[:2]
    center_x = int(location[0] + width / 2)
    center_y = int(location[1] + height / 2)
    result = MatchResult(
        x=center_x,
        y=center_y,
        score=score,
        width=int(width),
        height=int(height),
        match_mode=mode,
        preview_data_url=_annotated_preview(Image, image_rgb, location, width, height, score, mode),
    )
    if score < float(threshold):
        prefix = source_label
        raise MatchFailure(
            f"{prefix}未达到识别阈值：最高相似度 {score:.3f}，阈值 {float(threshold):.3f}",
            result,
        )
    return result


def _load_mask(np, Image, mask_path, alpha, template_size):
    mask = None
    if str(mask_path or "").strip():
        path = _image_path(mask_path, "遮罩图")
        mask_image = Image.open(path).convert("L")
        if mask_image.size != template_size:
            raise ValueError("遮罩尺寸必须与模板图片完全一致。")
        mask = np.array(mask_image)
    elif np.any(alpha < 255):
        mask = alpha
    if mask is None:
        return None
    mask = np.where(mask >= 16, 255, 0).astype("uint8")
    if not np.any(mask):
        raise ValueError("遮罩没有包含任何有效像素。")
    return mask


def _resolve_mode(value, mask):
    mode = str(value or "grayscale").strip().lower()
    if mode not in MATCH_MODES:
        mode = "grayscale"
    if mode == "smart":
        return "masked_edge" if mask is not None else "edge"
    return mode


def _annotated_window_preview(Image, image_rgb, search_box, candidate_center, candidate_size, score, mode):
    from PIL import ImageDraw

    image = Image.fromarray(image_rgb).convert("RGB")
    draw = ImageDraw.Draw(image)
    search_left, search_top, search_right, search_bottom = search_box
    line_width = max(2, int(min(image.size) / 240))
    draw.rectangle(
        (search_left, search_top, max(search_left, search_right - 1), max(search_top, search_bottom - 1)),
        outline=(245, 190, 78),
        width=line_width,
    )

    center_x, center_y = candidate_center
    candidate_width, candidate_height = candidate_size
    candidate_left = int(center_x - candidate_width / 2)
    candidate_top = int(center_y - candidate_height / 2)
    candidate_right = candidate_left + int(candidate_width)
    candidate_bottom = candidate_top + int(candidate_height)
    draw.rectangle(
        (candidate_left, candidate_top, candidate_right, candidate_bottom),
        outline=(104, 220, 185),
        width=line_width,
    )
    label = f"{mode}  {score:.3f}"
    label_box = draw.textbbox((0, 0), label)
    label_width = label_box[2] - label_box[0] + 12
    label_height = label_box[3] - label_box[1] + 8
    label_top = max(0, candidate_top - label_height)
    draw.rectangle(
        (candidate_left, label_top, candidate_left + label_width, label_top + label_height),
        fill=(19, 43, 37),
    )
    draw.text((candidate_left + 6, label_top + 3), label, fill=(214, 251, 240))
    return _preview_data_url(Image, image)

def _annotated_preview(Image, image_rgb, location, width, height, score, mode):
    from PIL import ImageDraw

    image = Image.fromarray(image_rgb).convert("RGB")
    draw = ImageDraw.Draw(image)
    left, top = location
    right = left + width
    bottom = top + height
    line_width = max(2, int(min(image.size) / 240))
    draw.rectangle((left, top, right, bottom), outline=(104, 220, 185), width=line_width)
    label = f"{mode}  {score:.3f}"
    label_box = draw.textbbox((0, 0), label)
    label_width = label_box[2] - label_box[0] + 12
    label_height = label_box[3] - label_box[1] + 8
    label_top = max(0, top - label_height)
    draw.rectangle((left, label_top, left + label_width, label_top + label_height), fill=(19, 43, 37))
    draw.text((left + 6, label_top + 3), label, fill=(214, 251, 240))

    return _preview_data_url(Image, image)


def _preview_data_url(Image, image):
    max_edge = 1100
    if max(image.size) > max_edge:
        scale = max_edge / max(image.size)
        image = image.resize(
            (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
            Image.Resampling.LANCZOS,
        )
    stream = io.BytesIO()
    image.save(stream, format="JPEG", quality=82, optimize=True)
    encoded = base64.b64encode(stream.getvalue()).decode("ascii")
    return "data:image/jpeg;base64," + encoded


def _image_path(value, label):
    path = os.path.abspath(os.path.expanduser(value or ""))
    if not os.path.exists(path):
        raise FileNotFoundError(f"{label}不存在：{path}")
    return path
