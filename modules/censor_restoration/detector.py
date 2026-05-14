from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .config import CensorRestorationConfig

try:
    import cv2
except ImportError:  # pragma: no cover - exercised only when OpenCV is absent.
    cv2 = None


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


class CensorMaskDetector:
    def __init__(self, config: Optional[CensorRestorationConfig] = None) -> None:
        self.config = config or CensorRestorationConfig()

    def detect(self, image: Any) -> DetectionResult:
        arr = self._to_numpy(image)
        if arr.ndim < 2:
            raise ValueError("image must be a 2D or 3D image")

        height, width = arr.shape[:2]
        gray = self._to_gray(arr)
        debug: Dict[str, Any] = {}
        boxes: List[CensorBox] = []

        if self.config.enable_dark_bar_detection:
            dark_mask = (gray < self.config.dark_threshold).astype(np.uint8) * 255
            dark_mask = self._morph(dark_mask)
            boxes.extend(self._boxes_from_mask(dark_mask, "dark", width, height))
            if self.config.save_debug_masks:
                debug["dark_candidates"] = dark_mask

        if self.config.enable_light_bar_detection:
            light_mask = (gray > self.config.light_threshold).astype(np.uint8) * 255
            light_mask = self._morph(light_mask)
            boxes.extend(self._boxes_from_mask(light_mask, "light", width, height))
            if self.config.save_debug_masks:
                debug["light_candidates"] = light_mask

        if self.config.merge_nearby_boxes:
            boxes = self._merge_boxes(boxes, width, height)

        final_mask = np.zeros((height, width), dtype=np.uint8)
        padded_boxes = [self._pad_box(box, width, height) for box in boxes]
        for box in padded_boxes:
            final_mask[box.y:box.y + box.height, box.x:box.x + box.width] = 255

        return DetectionResult(mask=final_mask, boxes=padded_boxes, debug=debug)

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

    def _morph(self, mask: np.ndarray) -> np.ndarray:
        size = max(1, int(self.config.morph_kernel_size))
        if size <= 1:
            return mask

        if cv2 is not None:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (size, size))
            closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            return cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel)

        return mask

    def _boxes_from_mask(self, mask: np.ndarray, kind: str, width: int, height: int) -> List[CensorBox]:
        if cv2 is not None:
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            raw_boxes = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                area = float(cv2.contourArea(contour))
                raw_boxes.append((x, y, w, h, area))
        else:
            raw_boxes = self._connected_component_boxes(mask)

        return [
            box for box in (
                self._candidate_box(raw_box, kind, width, height)
                for raw_box in raw_boxes
            )
            if box is not None
        ]

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
    ) -> Optional[CensorBox]:
        x, y, width, height, area = raw_box
        if width < self.config.min_width or height < self.config.min_height:
            return None

        image_area = max(1, image_width * image_height)
        area_ratio = area / image_area
        if area_ratio < self.config.min_area_ratio or area_ratio > self.config.max_area_ratio:
            return None

        aspect_ratio = max(width / max(1, height), height / max(1, width))
        if aspect_ratio < self.config.min_aspect_ratio:
            return None

        extent = area / max(1, width * height)
        if extent < 0.55:
            return None

        return CensorBox(x=x, y=y, width=width, height=height, score=extent, kind=kind)

    def _pad_box(self, box: CensorBox, image_width: int, image_height: int) -> CensorBox:
        padding = max(0, int(self.config.mask_padding))
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
        padding = max(0, int(self.config.mask_padding))
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
