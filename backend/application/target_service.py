import base64
import binascii
import io
import os
import re
import threading
from copy import deepcopy

from PIL import Image, UnidentifiedImageError


MAX_TEMPLATE_BYTES = 12 * 1024 * 1024
MAX_TEMPLATE_EDGE = 12000


class TargetService:
    def __init__(self, document, base_dir, save_targets=None, replace_references=None):
        self.base_dir = os.path.abspath(base_dir)
        self._save_targets = save_targets
        self._replace_references = replace_references
        self._lock = threading.RLock()
        self._document = self._normalize_document(document)

    def document(self):
        with self._lock:
            return deepcopy(self._document)

    def replace(self, document, point_renames=None, image_target_renames=None):
        if not isinstance(document, dict) or not document.get("point_groups"):
            raise ValueError("至少需要保留一个点位组")
        normalized = self._normalize_document(document)
        self._validate(normalized)
        point_renames = self._clean_renames(point_renames)
        image_target_renames = self._clean_renames(image_target_renames)
        with self._lock:
            if self._save_targets:
                self._save_targets(normalized, point_renames, image_target_renames)
            self._document = normalized
            if self._replace_references:
                self._replace_references(point_renames, image_target_renames)
            return deepcopy(self._document)

    def template_path(self, target_name):
        with self._lock:
            target = next((item for item in self._document["image_targets"] if item["name"] == target_name), None)
            if target is None:
                raise ValueError("图像目标不存在")
            raw_path = target["template_path"]
        path = raw_path if os.path.isabs(raw_path) else os.path.join(self.base_dir, raw_path)
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            raise ValueError("模板图片不存在")
        try:
            with Image.open(path) as image:
                image.verify()
        except (OSError, UnidentifiedImageError) as exc:
            raise ValueError("模板文件不是有效图片") from exc
        return path

    def mask_path(self, target_name):
        with self._lock:
            target = next((item for item in self._document["image_targets"] if item["name"] == target_name), None)
            if target is None:
                raise ValueError("图像目标不存在")
            raw_path = target.get("mask_path", "")
        if not raw_path:
            raise ValueError("图像目标尚未设置遮罩")
        path = raw_path if os.path.isabs(raw_path) else os.path.join(self.base_dir, raw_path)
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            raise ValueError("遮罩图片不存在")
        try:
            with Image.open(path) as image:
                image.verify()
        except (OSError, UnidentifiedImageError) as exc:
            raise ValueError("遮罩文件不是有效图片") from exc
        return path

    def import_mask(self, target_name, data_url, filename=""):
        target_name = str(target_name or "").strip()
        if not target_name:
            raise ValueError("请先填写图像目标名称")
        raw = self._decode_data_url(data_url)
        try:
            with Image.open(io.BytesIO(raw)) as source:
                source.load()
                if source.width > MAX_TEMPLATE_EDGE or source.height > MAX_TEMPLATE_EDGE:
                    raise ValueError("遮罩图片尺寸过大")
                if "A" in source.getbands():
                    alpha = source.getchannel("A")
                    extrema = alpha.getextrema()
                    mask = alpha if extrema != (255, 255) else source.convert("L")
                else:
                    mask = source.convert("L")
                mask = mask.point(lambda value: 255 if value >= 16 else 0, mode="1").convert("L")
        except (OSError, UnidentifiedImageError) as exc:
            raise ValueError("遮罩内容不是有效图片") from exc
        if mask.getbbox() is None:
            raise ValueError("遮罩没有包含任何有效像素")

        template_dir = os.path.join(self.base_dir, "image_templates")
        os.makedirs(template_dir, exist_ok=True)
        stem = os.path.splitext(os.path.basename(str(filename or "")))[0] or target_name + "_mask"
        stem = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", stem).strip("._") or "mask"
        if not stem.lower().endswith("_mask"):
            stem += "_mask"
        path = os.path.join(template_dir, f"{stem}.png")
        index = 2
        while os.path.exists(path):
            path = os.path.join(template_dir, f"{stem}_{index}.png")
            index += 1
        mask.save(path, format="PNG")
        return {
            "template_path": os.path.relpath(path, self.base_dir).replace("\\", "/"),
            "width": mask.width,
            "height": mask.height,
        }

    def import_template(self, target_name, data_url, filename=""):
        target_name = str(target_name or "").strip()
        if not target_name:
            raise ValueError("请先填写图像目标名称")
        raw = self._decode_data_url(data_url)
        try:
            with Image.open(io.BytesIO(raw)) as source:
                source.load()
                if source.width > MAX_TEMPLATE_EDGE or source.height > MAX_TEMPLATE_EDGE:
                    raise ValueError("模板图片尺寸过大")
                image = source.convert("RGBA")
        except (OSError, UnidentifiedImageError) as exc:
            raise ValueError("剪贴板或文件内容不是有效图片") from exc

        template_dir = os.path.join(self.base_dir, "image_templates")
        os.makedirs(template_dir, exist_ok=True)
        stem = os.path.splitext(os.path.basename(str(filename or "")))[0] or target_name
        stem = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", stem).strip("._") or "template"
        path = os.path.join(template_dir, f"{stem}.png")
        index = 2
        while os.path.exists(path):
            path = os.path.join(template_dir, f"{stem}_{index}.png")
            index += 1
        image.save(path, format="PNG")
        return {
            "template_path": os.path.relpath(path, self.base_dir).replace("\\", "/"),
            "width": image.width,
            "height": image.height,
        }

    @staticmethod
    def _decode_data_url(data_url):
        value = str(data_url or "")
        if "," not in value or not value.startswith("data:image/"):
            raise ValueError("图片数据格式无效")
        encoded = value.split(",", 1)[1]
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("图片数据无法解码") from exc
        if not raw or len(raw) > MAX_TEMPLATE_BYTES:
            raise ValueError("模板图片为空或超过 12 MB")
        return raw

    @staticmethod
    def _clean_renames(value):
        if not isinstance(value, dict):
            return {}
        return {
            str(old).strip(): str(new).strip()
            for old, new in value.items()
            if str(old).strip() and str(new).strip() and str(old).strip() != str(new).strip()
        }

    @classmethod
    def _normalize_document(cls, data):
        data = data if isinstance(data, dict) else {}
        groups = []
        for item in data.get("point_groups", []):
            points = []
            for point in item.get("points", []):
                points.append({
                    "name": str(point.get("name", "")).strip(),
                    "x": cls._integer(point.get("x", 0)),
                    "y": cls._integer(point.get("y", 0)),
                })
            groups.append({"name": str(item.get("name", "")).strip(), "points": points})
        if not groups:
            legacy = data.get("points", [])
            groups = [{
                "name": str(data.get("active_point_group", "") or "逆水寒").strip(),
                "points": [
                    {"name": str(point.get("name", "")).strip(), "x": cls._integer(point.get("x", 0)), "y": cls._integer(point.get("y", 0))}
                    for point in legacy
                ],
            }]
        active = str(data.get("active_point_group", "")).strip()
        if active not in {group["name"] for group in groups}:
            active = groups[0]["name"]

        targets = []
        for item in data.get("image_targets", []):
            targets.append({
                "name": str(item.get("name", "")).strip(),
                "template_path": str(item.get("template_path", "")).strip(),
                "match_mode": str(item.get("match_mode", "grayscale")).strip().lower() or "grayscale",
                "mask_path": str(item.get("mask_path", "")).strip(),
                "edge_low": cls._integer(item.get("edge_low", 60)),
                "edge_high": cls._integer(item.get("edge_high", 160)),
                "region": str(item.get("region", "")).strip(),
                "threshold": cls._number(item.get("threshold", 0.85), 0.85),
                "offset_x": cls._integer(item.get("offset_x", 0)),
                "offset_y": cls._integer(item.get("offset_y", 0)),
                "retry_seconds": cls._number(item.get("retry_seconds", 3.0), 3.0),
            })
        return {"active_point_group": active, "point_groups": groups, "image_targets": targets}

    @staticmethod
    def _validate(document):
        groups = document["point_groups"]
        if not groups:
            raise ValueError("至少需要保留一个点位组")
        group_names = set()
        for group in groups:
            if not group["name"]:
                raise ValueError("点位组名称不能为空")
            if group["name"] in group_names:
                raise ValueError(f"点位组名称重复：{group['name']}")
            group_names.add(group["name"])
            point_names = set()
            for point in group["points"]:
                if not point["name"]:
                    raise ValueError("点位名称不能为空")
                if point["name"] in point_names:
                    raise ValueError(f"点位名称重复：{point['name']}")
                point_names.add(point["name"])

        target_names = set()
        for target in document["image_targets"]:
            if not target["name"]:
                raise ValueError("图像目标名称不能为空")
            if target["name"] in target_names:
                raise ValueError(f"图像目标名称重复：{target['name']}")
            target_names.add(target["name"])
            if not target["template_path"]:
                raise ValueError(f"图像目标“{target['name']}”尚未选择模板")
            if target["match_mode"] not in {"smart", "grayscale", "edge", "masked", "masked_edge"}:
                raise ValueError("未知的图像匹配方式")
            if target["match_mode"] in {"masked", "masked_edge"} and not target["mask_path"]:
                raise ValueError(f"图像目标“{target['name']}”需要先设置遮罩")
            if not 0 <= target["edge_low"] <= 255 or not 0 <= target["edge_high"] <= 255:
                raise ValueError("边缘阈值必须在 0 到 255 之间")
            if target["edge_low"] >= target["edge_high"]:
                raise ValueError("边缘高阈值必须大于低阈值")
            if not 0 <= target["threshold"] <= 1:
                raise ValueError("识别阈值必须在 0 到 1 之间")
            if target["retry_seconds"] < 0:
                raise ValueError("重试秒数不能小于 0")
            TargetService._validate_region(target["region"])

    @staticmethod
    def _validate_region(value):
        if not value:
            return
        parts = [item.strip() for item in value.split(",")]
        if len(parts) != 4:
            raise ValueError("识别区域需要包含 X、Y、宽度和高度")
        try:
            _x, _y, width, height = (int(item) for item in parts)
        except ValueError as exc:
            raise ValueError("识别区域只能填写整数") from exc
        if width <= 0 or height <= 0:
            raise ValueError("识别区域宽度和高度必须大于 0")

    @staticmethod
    def _integer(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _number(value, fallback):
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback
