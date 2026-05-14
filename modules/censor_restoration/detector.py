from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .config import CensorRestorationConfig

try:
    import cv2
except ImportError:  # pragma: no cover - exercised only when OpenCV is absent.
    cv2 = None


CENSOR_RESTORATION_MASK_ROLE = "censor_restoration"


@dataclass
class CensorBox:
    x: int
    y: int
    width: int
    height: int
    score: float = 0.0
    kind: str = "dark"


@dataclass
class DetectionResult:
    mask: np.ndarray
    boxes: List[CensorBox] = field(default_factory=list)
    debug: Dict[str, Any] = field(default_factory=dict)
    mask_role: str = CENSOR_RESTORATION_MASK_ROLE


class CensorMaskDetector:
    def __init__(self, config: Optional[CensorRestorationConfig] = None) -> None:
        self.config = config or CensorRestorationConfig()

    def detect(self, image: Any) -> DetectionResult:
        arr = self._to_numpy(image)
        if arr.ndim < 2:
            raise ValueError("image must be a 2D or 3D image")

        height, width = arr.shape[:2]
        gray = self._to_gray(arr)
        saturation = self._to_saturation(arr)
        debug: Dict[str, Any] = {
            "dark_contours": 0,
            "light_contours": 0,
            "gray_contours": 0,
            "banded_contours": 0,
            "blocky_contours": 0,
            "dark_candidates": 0,
            "light_candidates": 0,
            "gray_candidates": 0,
            "banded_candidates": 0,
            "blocky_candidates": 0,
            "accepted_boxes": 0,
            "rejected_boxes": 0,
            "rejection_reasons": {
                "too_small": 0,
                "too_large": 0,
                "not_rectangular": 0,
                "min_width_height": 0,
                "too_thin": 0,
                "border": 0,
                "likely_panel_line": 0,
                "likely_speech_bubble": 0,
                "likely_text_mask": 0,
                "outside_threshold": 0,
                "aspect_ratio": 0,
            },
            "thresholds": {
                "dark_threshold": self.config.dark_threshold,
                "light_threshold": self.config.light_threshold,
                "adaptive_threshold_enabled": self.config.adaptive_threshold_enabled,
                "gray_min_value": self.config.gray_min_value,
                "gray_max_value": self.config.gray_max_value,
                "gray_max_saturation": self.config.gray_max_saturation,
                "banded_gradient_threshold": self.config.banded_gradient_threshold,
                "min_banded_score": self.config.min_banded_score,
            },
        }
        boxes: List[CensorBox] = []

        if self.config.enable_dark_bar_detection:
            dark_mask = self._dark_candidate_mask(gray)
            dark_mask = self._morph(dark_mask)
            dark_boxes, dark_stats = self._boxes_from_mask(dark_mask, "dark", width, height, gray, saturation)
            boxes.extend(dark_boxes)
            self._merge_debug_stats(debug, dark_stats)
            debug["dark_candidates_mask"] = dark_mask

        if self.config.enable_light_bar_detection:
            light_mask = self._light_candidate_mask(gray)
            light_mask = self._morph(light_mask)
            light_boxes, light_stats = self._boxes_from_mask(light_mask, "light", width, height, gray, saturation)
            boxes.extend(light_boxes)
            self._merge_debug_stats(debug, light_stats)
            debug["light_candidates_mask"] = light_mask

        if self.config.enable_gray_censor_detection:
            gray_mask = self._gray_candidate_mask(gray, saturation)
            gray_mask = self._morph(gray_mask)
            gray_boxes, gray_stats = self._boxes_from_mask(gray_mask, "gray", width, height, gray, saturation)
            boxes.extend(gray_boxes)
            self._merge_debug_stats(debug, gray_stats)
            debug["gray_candidates_mask"] = gray_mask

        if self.config.enable_banded_censor_detection:
            banded_mask = self._banded_candidate_mask(gray, saturation)
            banded_mask = self._morph(banded_mask)
            banded_boxes, banded_stats = self._boxes_from_mask(banded_mask, "banded", width, height, gray, saturation)
            boxes.extend(banded_boxes)
            self._merge_debug_stats(debug, banded_stats)
            debug["banded_candidates_mask"] = banded_mask

        if self.config.merge_nearby_boxes:
            boxes = self._merge_boxes(boxes, width, height)

        final_mask = np.zeros((height, width), dtype=np.uint8)
        padded_boxes = [self._pad_box(box, width, height) for box in boxes]
        for box in padded_boxes:
            final_mask[box.y:box.y + box.height, box.x:box.x + box.width] = 255

        debug["final_box_count"] = len(padded_boxes)
        debug["accepted_boxes"] = len(padded_boxes)
        debug["mask_pixel_count"] = int(np.count_nonzero(final_mask))
        debug["mask_coverage_ratio"] = debug["mask_pixel_count"] / max(1, width * height)
        debug["final_mask"] = final_mask
        if self.config.save_debug_masks:
            debug["gray"] = gray

        return DetectionResult(mask=final_mask, boxes=padded_boxes, debug=debug, mask_role=CENSOR_RESTORATION_MASK_ROLE)

    def _merge_debug_stats(self, debug: Dict[str, Any], stats: Dict[str, Any]) -> None:
        debug["dark_contours"] += int(stats.get("dark_contours", 0))
        debug["light_contours"] += int(stats.get("light_contours", 0))
        debug["gray_contours"] += int(stats.get("gray_contours", 0))
        debug["banded_contours"] += int(stats.get("banded_contours", 0))
        debug["blocky_contours"] += int(stats.get("blocky_contours", 0))
        kind = stats.get("kind")
        if kind:
            debug[f"{kind}_candidates"] = debug.get(f"{kind}_candidates", 0) + int(stats.get("raw_count", 0))
        rejected_total = 0
        for key, value in stats.get("rejection_reasons", {}).items():
            debug["rejection_reasons"][key] = debug["rejection_reasons"].get(key, 0) + int(value)
            rejected_total += int(value)
        debug["rejected_boxes"] += rejected_total

    def _to_numpy(self, image: Any) -> np.ndarray:
        if isinstance(image, np.ndarray):
            arr = image
        elif hasattr(image, "__array__"):
            arr = np.asarray(image)
        elif hasattr(image, "convert"):
            arr = np.asarray(image.convert("RGB"))
        else:
            raise TypeError("image must be a NumPy array, PIL Image, or array-like image")

        if arr.dtype != np.uint8:
            arr = np.clip(arr, 0, 255).astype(np.uint8)
        return arr

    def _to_gray(self, arr: np.ndarray) -> np.ndarray:
        if arr.ndim == 2:
            return arr

        if arr.shape[2] == 4:
            arr = arr[:, :, :3]

        if cv2 is not None:
            return cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

        channels = arr.astype(np.float32)
        gray = channels[:, :, 0] * 0.299 + channels[:, :, 1] * 0.587 + channels[:, :, 2] * 0.114
        return np.clip(gray, 0, 255).astype(np.uint8)

    def _to_saturation(self, arr: np.ndarray) -> np.ndarray:
        if arr.ndim == 2:
            return np.zeros(arr.shape, dtype=np.uint8)
        rgb = arr[:, :, :3]
        if cv2 is not None:
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)[:, :, 1]
        rgb_f = rgb.astype(np.float32)
        maxc = rgb_f.max(axis=2)
        minc = rgb_f.min(axis=2)
        sat = np.zeros_like(maxc)
        active = maxc > 0
        sat[active] = (maxc[active] - minc[active]) / maxc[active] * 255.0
        return np.clip(sat, 0, 255).astype(np.uint8)

    def _morph(self, mask: np.ndarray) -> np.ndarray:
        size = max(1, int(self.config.morph_kernel_size))
        if size <= 1:
            return mask

        if cv2 is not None:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (size, size))
            closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            return cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel)

        return mask

    def _dark_candidate_mask(self, gray: np.ndarray) -> np.ndarray:
        fixed = gray < self.config.dark_threshold
        if not self.config.adaptive_threshold_enabled or cv2 is None:
            return fixed.astype(np.uint8) * 255
        local = cv2.blur(gray.astype(np.float32), (31, 31))
        adaptive = (gray.astype(np.float32) < (local - 42)) & (gray < max(120, self.config.gray_min_value + 45))
        return (fixed | adaptive).astype(np.uint8) * 255

    def _light_candidate_mask(self, gray: np.ndarray) -> np.ndarray:
        fixed = gray > self.config.light_threshold
        if not self.config.adaptive_threshold_enabled or cv2 is None:
            return fixed.astype(np.uint8) * 255
        local = cv2.blur(gray.astype(np.float32), (31, 31))
        adaptive = gray.astype(np.float32) > (local + 42)
        return (fixed | adaptive).astype(np.uint8) * 255

    def _gray_candidate_mask(self, gray: np.ndarray, saturation: np.ndarray) -> np.ndarray:
        gray_candidate = (
            (gray >= self.config.gray_min_value)
            & (gray <= self.config.gray_max_value)
            & (saturation <= self.config.gray_max_saturation)
        )
        return gray_candidate.astype(np.uint8) * 255

    def _banded_candidate_mask(self, gray: np.ndarray, saturation: np.ndarray) -> np.ndarray:
        if cv2 is None:
            return np.zeros_like(gray, dtype=np.uint8)

        gray_f = gray.astype(np.float32)
        grad_x = np.abs(cv2.Sobel(gray_f, cv2.CV_32F, 1, 0, ksize=3))
        grad_y = np.abs(cv2.Sobel(gray_f, cv2.CV_32F, 0, 1, ksize=3))
        directional = np.maximum(grad_x, grad_y)
        local_std = cv2.blur(gray_f * gray_f, (9, 9)) - cv2.blur(gray_f, (9, 9)) ** 2
        local_std = np.sqrt(np.maximum(local_std, 0))
        neutral = saturation <= max(45, self.config.gray_max_saturation)
        midtone = (gray >= self.config.gray_min_value) & (gray <= self.config.gray_max_value)
        banded = (
            neutral
            & midtone
            & (directional >= self.config.banded_gradient_threshold)
            & (local_std >= max(3.0, self.config.min_banded_score * 20.0))
        )
        return banded.astype(np.uint8) * 255

    def _boxes_from_mask(
        self,
        mask: np.ndarray,
        kind: str,
        width: int,
        height: int,
        gray: np.ndarray,
        saturation: np.ndarray,
    ) -> Tuple[List[CensorBox], Dict[str, Any]]:
        stats: Dict[str, Any] = {
            "kind": kind,
            "raw_count": 0,
            "dark_contours": 0,
            "light_contours": 0,
            "gray_contours": 0,
            "banded_contours": 0,
            "blocky_contours": 0,
            "rejection_reasons": {
                "too_small": 0,
                "too_large": 0,
                "aspect_ratio": 0,
                "not_rectangular": 0,
                "min_width_height": 0,
                "border": 0,
                "too_thin": 0,
                "likely_panel_line": 0,
                "likely_speech_bubble": 0,
                "likely_text_mask": 0,
                "outside_threshold": 0,
            },
        }
        if cv2 is not None:
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            raw_boxes = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                area = float(cv2.contourArea(contour))
                raw_boxes.append((x, y, w, h, area))
        else:
            raw_boxes = self._connected_component_boxes(mask)

        stats["raw_count"] = len(raw_boxes)
        stats[f"{kind}_contours"] = len(raw_boxes)
        boxes: List[CensorBox] = []
        for raw_box in raw_boxes:
            box, reject_reason = self._candidate_box(raw_box, kind, width, height, gray, saturation)
            if box is not None:
                boxes.append(box)
            elif reject_reason:
                stats["rejection_reasons"][reject_reason] = stats["rejection_reasons"].get(reject_reason, 0) + 1
        return boxes, stats

    def _connected_component_boxes(self, mask: np.ndarray) -> List[Tuple[int, int, int, int, float]]:
        visited = np.zeros(mask.shape, dtype=bool)
        boxes: List[Tuple[int, int, int, int, float]] = []
        ys, xs = np.where(mask > 0)
        active = set(zip(xs.tolist(), ys.tolist()))

        for start_x, start_y in list(active):
            if visited[start_y, start_x]:
                continue
            stack = [(start_x, start_y)]
            visited[start_y, start_x] = True
            min_x = max_x = start_x
            min_y = max_y = start_y
            area = 0

            while stack:
                x, y = stack.pop()
                area += 1
                min_x, max_x = min(min_x, x), max(max_x, x)
                min_y, max_y = min(min_y, y), max(max_y, y)
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if (nx, ny) in active and not visited[ny, nx]:
                        visited[ny, nx] = True
                        stack.append((nx, ny))

            boxes.append((min_x, min_y, max_x - min_x + 1, max_y - min_y + 1, float(area)))

        return boxes

    def _candidate_box(
        self,
        raw_box: Tuple[int, int, int, int, float],
        kind: str,
        image_width: int,
        image_height: int,
        gray: np.ndarray,
        saturation: np.ndarray,
    ) -> Tuple[Optional[CensorBox], Optional[str]]:
        x, y, width, height, area = raw_box
        if width < self.config.min_width or height < self.config.min_height:
            return None, "min_width_height"

        margin = max(0, int(self.config.ignore_page_border_margin))
        if margin > 0 and (x <= margin or y <= margin or x + width >= image_width - margin or y + height >= image_height - margin):
            if width > image_width * 0.35 or height > image_height * 0.35:
                return None, "border"

        if (self.config.ignore_very_thin_lines or self.config.ignore_thin_panel_lines) and min(width, height) <= 4:
            return None, "too_thin"
        if self.config.ignore_thin_panel_lines and min(width, height) <= 4 and max(width, height) > min(image_width, image_height) * 0.35:
            return None, "likely_panel_line"

        image_area = max(1, image_width * image_height)
        area_ratio = area / image_area
        min_area_ratio = self.config.min_area_ratio
        max_area_ratio = self.config.max_area_ratio
        if kind in {"gray", "banded"}:
            min_area_ratio = max(min_area_ratio, self.config.min_gray_area_ratio)
            max_area_ratio = min(max_area_ratio, self.config.max_gray_area_ratio)
        if area_ratio < min_area_ratio:
            return None, "too_small"
        if area_ratio > max_area_ratio:
            return None, "too_large"

        aspect_ratio = max(width / max(1, height), height / max(1, width))
        extent = area / max(1, width * height)
        min_extent = self.config.min_gray_rectangularity if kind in {"gray", "banded"} else 0.55
        if extent < min_extent:
            return None, "not_rectangular"

        roi_gray = gray[y:y + height, x:x + width]
        roi_sat = saturation[y:y + height, x:x + width]
        mean_value = float(np.mean(roi_gray)) if roi_gray.size else 0.0
        mean_sat = float(np.mean(roi_sat)) if roi_sat.size else 0.0
        std_value = float(np.std(roi_gray)) if roi_gray.size else 0.0
        if kind == "light" and area_ratio > 0.015 and aspect_ratio < self.config.min_aspect_ratio and mean_value > 244 and std_value < 6:
            return None, "likely_speech_bubble"
        if kind in {"gray", "banded"}:
            if mean_sat > max(55, self.config.gray_max_saturation + 20):
                return None, "outside_threshold"
            if mean_value >= 238 and std_value < 5:
                return None, "likely_text_mask"

        is_bar = aspect_ratio >= self.config.min_aspect_ratio
        is_block = (
            self.config.allow_blocky_regions
            and self.config.min_block_area_ratio <= area_ratio <= min(self.config.max_block_area_ratio, max_area_ratio)
        )
        if kind in {"gray", "banded"}:
            is_block = self.config.allow_blocky_regions and self.config.min_gray_area_ratio <= area_ratio <= max_area_ratio
        if not is_bar and not is_block:
            return None, "aspect_ratio"

        return CensorBox(x=x, y=y, width=width, height=height, score=extent, kind=kind), None

    def _pad_box(self, box: CensorBox, image_width: int, image_height: int) -> CensorBox:
        proportional = int(round(min(image_width, image_height) * 0.006))
        padding = max(0, int(self.config.mask_padding), proportional)
        x1 = max(0, box.x - padding)
        y1 = max(0, box.y - padding)
        x2 = min(image_width, box.x + box.width + padding)
        y2 = min(image_height, box.y + box.height + padding)
        return CensorBox(
            x=x1,
            y=y1,
            width=max(0, x2 - x1),
            height=max(0, y2 - y1),
            score=box.score,
            kind=box.kind,
        )

    def _merge_boxes(self, boxes: Sequence[CensorBox], image_width: int, image_height: int) -> List[CensorBox]:
        merged: List[CensorBox] = []
        for box in boxes:
            current = box
            did_merge = True
            while did_merge:
                did_merge = False
                remaining: List[CensorBox] = []
                for other in merged:
                    if current.kind == other.kind and self._boxes_close(current, other):
                        current = self._union_box(current, other, image_width, image_height)
                        did_merge = True
                    else:
                        remaining.append(other)
                merged = remaining
            merged.append(current)
        return merged

    def _boxes_close(self, first: CensorBox, second: CensorBox) -> bool:
        padding = max(0, int(self.config.merge_distance))
        ax1, ay1 = first.x - padding, first.y - padding
        ax2, ay2 = first.x + first.width + padding, first.y + first.height + padding
        bx1, by1 = second.x, second.y
        bx2, by2 = second.x + second.width, second.y + second.height
        return ax1 <= bx2 and ax2 >= bx1 and ay1 <= by2 and ay2 >= by1

    def _union_box(self, first: CensorBox, second: CensorBox, image_width: int, image_height: int) -> CensorBox:
        x1 = max(0, min(first.x, second.x))
        y1 = max(0, min(first.y, second.y))
        x2 = min(image_width, max(first.x + first.width, second.x + second.width))
        y2 = min(image_height, max(first.y + first.height, second.y + second.height))
        return CensorBox(
            x=x1,
            y=y1,
            width=max(0, x2 - x1),
            height=max(0, y2 - y1),
            score=max(first.score, second.score),
            kind=first.kind,
        )
