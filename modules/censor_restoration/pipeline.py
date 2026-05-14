from dataclasses import asdict, dataclass, field
import json
import os
import os.path as osp
from typing import Any, Dict, List, Optional

import numpy as np

from utils.logger import logger as LOGGER

from .detector import CENSOR_RESTORATION_MASK_ROLE, CensorBox, CensorMaskDetector

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
    mask_role: str = CENSOR_RESTORATION_MASK_ROLE
    input_source: str = "provided"
    input_size: Optional[tuple] = None
    mask_source: str = "detector"


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
        input_source: str = "provided",
    ) -> PipelineResult:
        original_image: Optional[np.ndarray] = None

        try:
            original_image = self._to_numpy(image)
            input_size = original_image.shape[:2]
            if self._looks_like_binary_mask(original_image):
                return PipelineResult(
                    status="error",
                    original_image=original_image,
                    result_image=original_image.copy(),
                    error_message="Invalid decensor input: image looks like a binary mask.",
                    input_source=input_source,
                    input_size=input_size,
                    mask_source="none",
                )

            detection = self.detector.detect(original_image)
            mask_role = getattr(detection, "mask_role", CENSOR_RESTORATION_MASK_ROLE)
            if mask_role != CENSOR_RESTORATION_MASK_ROLE:
                LOGGER.warning(f'Rejected non-censor mask role for Censor Restoration: {mask_role}')
                return PipelineResult(
                    status="error",
                    original_image=original_image,
                    result_image=original_image.copy(),
                    error_message="Censor Restoration only accepts censor_restoration masks.",
                    debug=detection.debug,
                    mask_role=mask_role,
                    input_source=input_source,
                    input_size=input_size,
                    mask_source="detector",
                )

            censor_mask = self._binary_mask(detection.mask)
            debug_paths = self._write_debug_outputs(
                original_image,
                censor_mask,
                detection.boxes,
                debug_output_dir,
                {**detection.debug, "input_source": input_source},
            )

            if int(censor_mask.sum()) == 0:
                return PipelineResult(
                    status="no_censor_mask_found",
                    original_image=original_image,
                    result_image=original_image.copy(),
                    mask=censor_mask,
                    boxes=[],
                    error_message="No censor mask found. The text inpaint mask will not be used automatically.",
                    debug_paths=debug_paths,
                    debug=detection.debug,
                    mask_role=mask_role,
                    input_source=input_source,
                    input_size=input_size,
                    mask_source="detector",
                )

            backend = inpainter or self.inpainter
            if backend is None:
                return PipelineResult(
                    status="error",
                    original_image=original_image,
                    result_image=original_image.copy(),
                    mask=censor_mask,
                    boxes=detection.boxes,
                    error_message="No inpainter is configured for censor restoration.",
                    debug_paths=debug_paths,
                    debug=detection.debug,
                    mask_role=mask_role,
                    input_source=input_source,
                    input_size=input_size,
                    mask_source="detector",
                )

            result_image = self._run_inpainter(backend, original_image.copy(), censor_mask)
            return PipelineResult(
                status="success",
                original_image=original_image,
                result_image=result_image,
                mask=censor_mask,
                boxes=detection.boxes,
                debug_paths=debug_paths,
                debug=detection.debug,
                mask_role=mask_role,
                input_source=input_source,
                input_size=input_size,
                mask_source="detector",
            )
        except Exception as exc:
            LOGGER.exception("Censor restoration pipeline failed")
            return PipelineResult(
                status="error",
                original_image=original_image,
                result_image=original_image.copy() if original_image is not None else None,
                error_message=f"{type(exc).__name__}: {exc}",
                input_source=input_source,
                input_size=original_image.shape[:2] if original_image is not None else None,
                mask_source="detector",
            )

    def run_with_manual_censor_mask(
        self,
        image: Any,
        censor_mask: Any,
        inpainter: Optional[Any] = None,
        debug_output_dir: Optional[str] = None,
        mask_role: str = CENSOR_RESTORATION_MASK_ROLE,
        input_source: str = "provided",
    ) -> PipelineResult:
        original_image: Optional[np.ndarray] = None
        try:
            original_image = self._to_numpy(image)
            input_size = original_image.shape[:2]
            if self._looks_like_binary_mask(original_image):
                return PipelineResult(
                    status="error",
                    original_image=original_image,
                    result_image=original_image.copy(),
                    error_message="Invalid decensor input: image looks like a binary mask.",
                    input_source=input_source,
                    input_size=input_size,
                    mask_source="manual",
                )
            if mask_role != CENSOR_RESTORATION_MASK_ROLE:
                LOGGER.warning(f'Rejected manual mask role for Censor Restoration: {mask_role}')
                return PipelineResult(
                    status="error",
                    original_image=original_image,
                    result_image=original_image.copy(),
                    error_message="Only explicit censor_restoration masks can be used for Censor Restoration.",
                    mask_role=mask_role,
                    input_source=input_source,
                    input_size=input_size,
                    mask_source="manual",
                )

            LOGGER.info("Using explicit manual censor mask.")
            normalized_mask = self._normalize_external_mask(censor_mask, original_image.shape[:2])
            debug = {
                "manual_mask": True,
                "mask_role": mask_role,
                "input_source": input_source,
                "mask_pixel_count": int(np.count_nonzero(normalized_mask)),
                "mask_coverage_ratio": int(np.count_nonzero(normalized_mask)) / max(1, normalized_mask.size),
            }
            if int(normalized_mask.sum()) == 0:
                return PipelineResult(
                    status="no_censor_mask_found",
                    original_image=original_image,
                    result_image=original_image.copy(),
                    mask=normalized_mask,
                    boxes=[],
                    error_message="No censor mask found. The text inpaint mask will not be used automatically.",
                    debug=debug,
                    mask_role=mask_role,
                    input_source=input_source,
                    input_size=input_size,
                    mask_source="manual",
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
                    mask_role=mask_role,
                    input_source=input_source,
                    input_size=input_size,
                    mask_source="manual",
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
                mask_role=mask_role,
                input_source=input_source,
                input_size=input_size,
                mask_source="manual",
            )
        except Exception as exc:
            LOGGER.exception("Censor restoration manual-mask pipeline failed")
            return PipelineResult(
                status="error",
                original_image=original_image,
                result_image=original_image.copy() if original_image is not None else None,
                error_message=f"{type(exc).__name__}: {exc}",
                mask_role=mask_role,
                input_source=input_source,
                input_size=original_image.shape[:2] if original_image is not None else None,
                mask_source="manual",
            )

    def run_with_mask(
        self,
        image: Any,
        mask: Any,
        inpainter: Optional[Any] = None,
        debug_output_dir: Optional[str] = None,
        mask_role: str = CENSOR_RESTORATION_MASK_ROLE,
    ) -> PipelineResult:
        return self.run_with_manual_censor_mask(
            image,
            mask,
            inpainter=inpainter,
            debug_output_dir=debug_output_dir,
            mask_role=mask_role,
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

    def _looks_like_binary_mask(self, image: np.ndarray) -> bool:
        if image.ndim != 2:
            return False
        values = image
        unique = np.unique(values)
        if unique.size > 4:
            return False
        if not np.all(np.isin(unique, [0, 1, 255])):
            return False
        active_ratio = float(np.count_nonzero(values)) / max(1, values.size)
        return 0.005 <= active_ratio <= 0.995

    def _write_debug_outputs(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        boxes: List[CensorBox],
        debug_output_dir: Optional[str],
        debug: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        detector_config = getattr(self.detector, "config", None)
        if not getattr(detector_config, "save_debug_masks", False) or not debug_output_dir:
            return {}

        os.makedirs(debug_output_dir, exist_ok=True)
        mask_path = osp.join(debug_output_dir, "_final_mask.png")
        overlay_path = osp.join(debug_output_dir, "_boxes_overlay.png")
        boxes_path = osp.join(debug_output_dir, "_detection.json")

        self._write_png(mask_path, mask)
        self._write_png(overlay_path, self._mask_overlay(image, mask))
        debug_payload = self._json_safe_debug(debug or {})
        debug_payload["boxes"] = [asdict(box) for box in boxes]
        debug_payload["mask_role"] = CENSOR_RESTORATION_MASK_ROLE
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
                ("dark_candidates_mask", "_dark_candidates.png"),
                ("light_candidates_mask", "_light_candidates.png"),
                ("gray_candidates_mask", "gray_candidates.png"),
                ("banded_candidates_mask", "banded_candidates.png"),
                ("final_mask", "accepted_censor_mask.png"),
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
