from dataclasses import asdict, dataclass, field
import json
import os
import os.path as osp
from typing import Any, Dict, List, Optional

import numpy as np

from utils.logger import logger as LOGGER

from .detector import CensorBox, CensorMaskDetector

try:
    import cv2
except ImportError:  # pragma: no cover - exercised only when OpenCV is absent.
    cv2 = None


@dataclass
class PipelineResult:
    status: str
    original_image: Optional[np.ndarray] = None
    result_image: Optional[np.ndarray] = None
    mask: Optional[np.ndarray] = None
    boxes: List[CensorBox] = field(default_factory=list)
    error_message: Optional[str] = None
    debug_paths: Dict[str, str] = field(default_factory=dict)
    debug: Dict[str, Any] = field(default_factory=dict)


class CensorRestorationPipeline:
    def __init__(
        self,
        detector: Optional[CensorMaskDetector] = None,
        inpainter: Optional[Any] = None,
    ) -> None:
        self.detector = detector or CensorMaskDetector()
        self.inpainter = inpainter

    def run(
        self,
        image: Any,
        inpainter: Optional[Any] = None,
        debug_output_dir: Optional[str] = None,
    ) -> PipelineResult:
        original_image: Optional[np.ndarray] = None

        try:
            original_image = self._to_numpy(image)
            detection = self.detector.detect(original_image)
            mask = self._binary_mask(detection.mask)
            debug_paths = self._write_debug_outputs(
                original_image,
                mask,
                detection.boxes,
                debug_output_dir,
                detection.debug,
            )

            if int(mask.sum()) == 0:
                return PipelineResult(
                    status="no_mask_found",
                    original_image=original_image,
                    result_image=original_image.copy(),
                    mask=mask,
                    boxes=[],
                    debug_paths=debug_paths,
                    debug=detection.debug,
                )

            backend = inpainter or self.inpainter
            if backend is None:
                return PipelineResult(
                    status="error",
                    original_image=original_image,
                    result_image=original_image.copy(),
                    mask=mask,
                    boxes=detection.boxes,
                    error_message="No inpainter is configured for censor restoration.",
                    debug_paths=debug_paths,
                    debug=detection.debug,
                )

            result_image = self._run_inpainter(backend, original_image.copy(), mask)
            return PipelineResult(
                status="success",
                original_image=original_image,
                result_image=result_image,
                mask=mask,
                boxes=detection.boxes,
                debug_paths=debug_paths,
                debug=detection.debug,
            )
        except Exception as exc:
            LOGGER.exception("Censor restoration pipeline failed")
            return PipelineResult(
                status="error",
                original_image=original_image,
                result_image=original_image.copy() if original_image is not None else None,
                error_message=f"{type(exc).__name__}: {exc}",
            )

    def run_with_mask(
        self,
        image: Any,
        mask: Any,
        inpainter: Optional[Any] = None,
        debug_output_dir: Optional[str] = None,
    ) -> PipelineResult:
        original_image: Optional[np.ndarray] = None
        try:
            original_image = self._to_numpy(image)
            normalized_mask = self._normalize_external_mask(mask, original_image.shape[:2])
            debug = {
                "manual_mask": True,
                "mask_pixel_count": int(np.count_nonzero(normalized_mask)),
                "mask_coverage_ratio": int(np.count_nonzero(normalized_mask)) / max(1, normalized_mask.size),
            }
            if int(normalized_mask.sum()) == 0:
                return PipelineResult(
                    status="no_mask_found",
                    original_image=original_image,
                    result_image=original_image.copy(),
                    mask=normalized_mask,
                    boxes=[],
                    debug=debug,
                )

            backend = inpainter or self.inpainter
            if backend is None:
                return PipelineResult(
                    status="error",
                    original_image=original_image,
                    result_image=original_image.copy(),
                    mask=normalized_mask,
                    boxes=[],
                    error_message="No inpainter is configured for censor restoration.",
                    debug=debug,
                )

            debug_paths = self._write_debug_outputs(
                original_image,
                normalized_mask,
                [],
                debug_output_dir,
                debug,
            )
            result_image = self._run_inpainter(backend, original_image.copy(), normalized_mask)
            return PipelineResult(
                status="success",
                original_image=original_image,
                result_image=result_image,
                mask=normalized_mask,
                boxes=[],
                debug_paths=debug_paths,
                debug=debug,
            )
        except Exception as exc:
            LOGGER.exception("Censor restoration manual-mask pipeline failed")
            return PipelineResult(
                status="error",
                original_image=original_image,
                result_image=original_image.copy() if original_image is not None else None,
                error_message=f"{type(exc).__name__}: {exc}",
            )

    def _run_inpainter(self, inpainter: Any, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        if hasattr(inpainter, "inpaint"):
            return inpainter.inpaint(image, mask, textblock_list=None)
        if callable(inpainter):
            return inpainter(image, mask)
        raise TypeError("Configured inpainter must expose inpaint(image, mask, ...) or be callable.")

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
        return arr.copy()

    def _binary_mask(self, mask: np.ndarray) -> np.ndarray:
        return np.where(mask > 0, 255, 0).astype(np.uint8)

    def _normalize_external_mask(self, mask: Any, image_shape: tuple) -> np.ndarray:
        mask_arr = self._to_numpy(mask)
        if mask_arr.ndim == 3:
            mask_arr = mask_arr[:, :, 0]
        if mask_arr.shape[:2] != image_shape:
            raise ValueError(
                f"mask shape {mask_arr.shape[:2]} does not match image shape {image_shape}"
            )
        return self._binary_mask(mask_arr)

    def _write_debug_outputs(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        boxes: List[CensorBox],
        debug_output_dir: Optional[str],
        debug: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        if not self.detector.config.save_debug_masks or not debug_output_dir:
            return {}

        os.makedirs(debug_output_dir, exist_ok=True)
        mask_path = osp.join(debug_output_dir, "_final_mask.png")
        overlay_path = osp.join(debug_output_dir, "_boxes_overlay.png")
        boxes_path = osp.join(debug_output_dir, "_detection.json")

        self._write_png(mask_path, mask)
        self._write_png(overlay_path, self._mask_overlay(image, mask))
        debug_payload = self._json_safe_debug(debug or {})
        debug_payload["boxes"] = [asdict(box) for box in boxes]
        with open(boxes_path, "w", encoding="utf8") as f:
            json.dump(debug_payload, f, indent=2)

        paths = {
            "mask": mask_path,
            "overlay": overlay_path,
            "detection": boxes_path,
        }

        if debug:
            for key, filename in (
                ("gray", "_gray.png"),
                ("dark_candidates", "_dark_candidates.png"),
                ("light_candidates", "_light_candidates.png"),
            ):
                image_data = debug.get(key)
                if isinstance(image_data, np.ndarray):
                    path = osp.join(debug_output_dir, filename)
                    self._write_png(path, image_data)
                    paths[key] = path

        return paths

    def _json_safe_debug(self, debug: Dict[str, Any]) -> Dict[str, Any]:
        safe: Dict[str, Any] = {}
        for key, value in debug.items():
            if isinstance(value, np.ndarray):
                continue
            safe[key] = value
        return safe

    def _mask_overlay(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        if image.ndim == 2:
            base = np.repeat(image[:, :, None], 3, axis=2)
        else:
            base = image[:, :, :3].copy()

        overlay = base.copy()
        active = mask > 0
        overlay[active] = (0.55 * overlay[active] + 0.45 * np.array([255, 0, 0])).astype(np.uint8)
        return overlay

    def _write_png(self, path: str, image: np.ndarray) -> None:
        if cv2 is not None:
            output = image
            if image.ndim == 3 and image.shape[2] == 3:
                output = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            if not cv2.imwrite(path, output):
                raise OSError(f"Failed to write debug image: {path}")
            return

        from PIL import Image
        Image.fromarray(image).save(path)
