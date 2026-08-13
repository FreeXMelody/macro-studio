import os

from automation import find_window
from vision import MatchFailure, locate_template, locate_template_in_window


class VisionTestService:
    def __init__(self, config_provider, base_dir, find_target_window=None, locate_screen=None, locate_window=None):
        self.config_provider = config_provider
        self.base_dir = os.path.abspath(base_dir)
        self.find_target_window = find_target_window or find_window
        self.locate_screen = locate_screen or locate_template
        self.locate_window = locate_window or locate_template_in_window

    def test(self, target):
        target = target if isinstance(target, dict) else {}
        path = self._resolve_path(target.get("template_path", ""))
        if not path:
            raise ValueError("图像目标尚未选择模板")
        if not os.path.isfile(path):
            raise ValueError("模板图片不存在")
        mask_path = self._resolve_path(target.get("mask_path", ""))
        if mask_path and not os.path.isfile(mask_path):
            raise ValueError("遮罩图片不存在")

        config = self.config_provider()
        window_hint = str(config.get("window_hint", "")).strip() if isinstance(config, dict) else ""
        region = str(target.get("region", "")).strip()
        threshold = float(target.get("threshold", 0.85))
        match_mode = str(target.get("match_mode", "grayscale"))
        edge_low = int(target.get("edge_low", 60))
        edge_high = int(target.get("edge_high", 160))
        window = self.find_target_window(window_hint) if window_hint else None
        if window_hint and not window:
            raise ValueError(f"找不到目标窗口：{window_hint}")

        source = "background" if window else "screen"
        args = (region, threshold, match_mode, mask_path, edge_low, edge_high)
        try:
            if window:
                match = self.locate_window(path, int(window["hwnd"]), *args)
            else:
                match = self.locate_screen(path, *args)
        except RuntimeError as exc:
            result = exc.result if isinstance(exc, MatchFailure) else None
            return {
                "matched": False,
                "source": source,
                "x": int(result.x) if result else 0,
                "y": int(result.y) if result else 0,
                "score": float(result.score) if result else 0,
                "width": int(result.width) if result else 0,
                "height": int(result.height) if result else 0,
                "match_mode": result.match_mode if result else match_mode,
                "preview_data_url": result.preview_data_url if result else "",
                "search_x": int(result.search_x) if result else 0,
                "search_y": int(result.search_y) if result else 0,
                "search_width": int(result.search_width) if result else 0,
                "search_height": int(result.search_height) if result else 0,
                "capture_width": int(result.capture_width) if result else 0,
                "capture_height": int(result.capture_height) if result else 0,
                "error": str(exc),
            }
        return {
            "matched": True,
            "source": source,
            "x": int(match.x),
            "y": int(match.y),
            "score": float(match.score),
            "width": int(match.width),
            "height": int(match.height),
            "match_mode": match.match_mode,
            "preview_data_url": match.preview_data_url,
            "search_x": int(match.search_x),
            "search_y": int(match.search_y),
            "search_width": int(match.search_width),
            "search_height": int(match.search_height),
            "capture_width": int(match.capture_width),
            "capture_height": int(match.capture_height),
        }

    def _resolve_path(self, value):
        path = str(value or "").strip()
        if path and not os.path.isabs(path):
            path = os.path.abspath(os.path.join(self.base_dir, path))
        return path