import numpy as np
import cv2
from typing import List, Optional

from ballontranslator.utils.registry import Registry
from ballontranslator.utils.textblock_mask import extract_ballon_mask
from ballontranslator.utils.imgproc_utils import enlarge_window, rotate_polygons, xywh2xyxypoly
from ballontranslator.utils.config import pcfg

from ..base import BaseModule, soft_empty_cache, require_torch
from ..textdetector import TextBlock

INPAINTERS = Registry('inpainters')
register_inpainter = INPAINTERS.register_module

# Keep this file limited to shared base logic; concrete inpainters live elsewhere.


def filter_mask_by_bboxes(mask: np.ndarray, textblock_list: List[TextBlock] = None) -> np.ndarray:
    """Keep mask pixels inside detected text block rects, with a small margin.

    Example:
        >>> mask = np.full((4, 5), 255, dtype=np.uint8)
        >>> blk = TextBlock(xyxy=[1, 1, 3, 2], _bounding_rect=[1, 1, 2, 1])
        >>> filtered = filter_mask_by_bboxes(mask, [blk])
        >>> filtered.tolist()
        [[255, 255, 255, 255, 255], [255, 255, 255, 255, 255], [255, 255, 255, 255, 255], [255, 255, 255, 255, 255]]
    """
    if mask is None or not textblock_list:
        return mask

    rect_mask = np.zeros_like(mask)
    for blk in textblock_list:
        x1, y1, bbox_w, bbox_h = np.array(blk.bounding_rect()).astype(np.int64)
        y2, x2 = y1 + bbox_h, x1 + bbox_w
        if bbox_w <= 0 or bbox_h <= 0:
            continue
        rect = xywh2xyxypoly(np.array([[x1, y1, bbox_w, bbox_h]]))
        if blk.angle != 0:
            rect = rotate_polygons([x1 + bbox_w / 2, y1 + bbox_h / 2], rect, -blk.angle)
        rect = rect.reshape(-1, 4, 2).astype(np.int32)
        cv2.fillPoly(rect_mask, [rect], 255)
        cv2.polylines(rect_mask, [rect], True, 255, 1)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    rect_mask = cv2.dilate(rect_mask, kernel)
    return cv2.bitwise_and(mask, rect_mask)


def inpaint_handle_alpha_channel(original_alpha, mask):
    '''
    perhaps a better idea is to feed the alpha into inpainting model, but it'll double the cost  
    for now it just return the original alpha
    '''

    result_alpha = original_alpha.copy()

    # Analyze the alpha values around the original mask to determine appropriate transparency
    mask_dilated = cv2.dilate((mask > 127).astype(np.uint8), np.ones((15, 15), np.uint8), iterations=1)
    surrounding_mask = mask_dilated - (mask > 127).astype(np.uint8)

    if np.any(surrounding_mask > 0):
        surrounding_alpha = original_alpha[surrounding_mask > 0]
        if len(surrounding_alpha) > 0:
            median_surrounding_alpha = np.median(surrounding_alpha)
            # If surrounding area is mostly transparent (median alpha < 128),
            # make inpainted areas transparent too
            if median_surrounding_alpha < 128:
                inpainted_mask = (mask > 127)
                result_alpha[inpainted_mask] = median_surrounding_alpha

    return result_alpha

class InpainterBase(BaseModule):

    inpaint_by_block = True

    def __init__(self, **params) -> None:
        super().__init__(**params)
        self.name = ''
        for key in INPAINTERS.module_dict:
            if INPAINTERS.module_dict[key] == self.__class__:
                self.name = key
                break

    def mask_dilation_size(self) -> int:
        if self.params is None or 'mask_dilation_size' not in self.params:
            return 0
        return max(0, int(self.get_param_value('mask_dilation_size')))

    def mask_dilation_kernel(self) -> str:
        if self.params is None or 'mask_dilation_kernel' not in self.params:
            return 'ellipse'
        kernel = str(self.get_param_value('mask_dilation_kernel'))
        return kernel if kernel in {'ellipse', 'rectangle', 'cross'} else 'ellipse'

    def mask_closing_size(self) -> int:
        if self.params is None or 'mask_closing_size' not in self.params:
            return 0
        return max(0, int(self.get_param_value('mask_closing_size')))

    def mask_closing_iterations(self) -> int:
        if self.params is None or 'mask_closing_iterations' not in self.params:
            return 1
        return max(
            1,
            min(5, int(self.get_param_value('mask_closing_iterations'))),
        )

    def mask_closing_kernel(self) -> str:
        if self.params is None or 'mask_closing_kernel' not in self.params:
            return 'ellipse'
        kernel = str(self.get_param_value('mask_closing_kernel'))
        return kernel if kernel in {'ellipse', 'rectangle', 'cross'} else 'ellipse'

    def mask_hole_fill_area(self) -> int:
        if self.params is None or 'mask_hole_fill_area' not in self.params:
            return 0
        return max(0, int(self.get_param_value('mask_hole_fill_area')))

    def inpaint_enlarge_ratio(self) -> float:
        if self.params is None or 'inpaint_enlarge_ratio' not in self.params:
            return 1.7
        return max(1.0, float(self.get_param_value('inpaint_enlarge_ratio')))

    @staticmethod
    def _kernel_shape(name: str) -> int:
        return {
            'ellipse': cv2.MORPH_ELLIPSE,
            'rectangle': cv2.MORPH_RECT,
            'cross': cv2.MORPH_CROSS,
        }[name]

    @staticmethod
    def _fill_small_mask_holes(
        mask: np.ndarray, max_area: int,
    ) -> np.ndarray:
        """Fill enclosed background components up to ``max_area`` pixels.

        Exterior background always remains untouched, preventing a fragmented
        text mask from expanding into unrelated artwork.

        >>> ring = np.full((3, 3), 255, np.uint8)
        >>> ring[1, 1] = 0
        >>> int(InpainterBase._fill_small_mask_holes(ring, 1)[1, 1])
        255
        """
        if max_area <= 0:
            return mask
        background = (mask == 0).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(
            background, connectivity=8,
        )
        border_labels = set(np.concatenate((
            labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1],
        )).tolist())
        repaired = mask.copy()
        for label in range(1, count):
            if (
                label not in border_labels
                and int(stats[label, cv2.CC_STAT_AREA]) <= max_area
            ):
                repaired[labels == label] = 255
        return repaired

    def repair_inpaint_mask(
        self, mask: Optional[np.ndarray],
    ) -> Optional[np.ndarray]:
        """Close small gaps and fill bounded pinholes without outer dilation."""
        if mask is None:
            return mask
        closing_size = self.mask_closing_size()
        max_hole_area = self.mask_hole_fill_area()
        if closing_size <= 0 and max_hole_area <= 0:
            return mask
        repaired = (mask > 0).astype(np.uint8) * 255
        if closing_size > 0:
            closing_size += 1 - closing_size % 2
            kernel = cv2.getStructuringElement(
                self._kernel_shape(self.mask_closing_kernel()),
                (closing_size, closing_size),
            )
            repaired = cv2.morphologyEx(
                repaired,
                cv2.MORPH_CLOSE,
                kernel,
                iterations=self.mask_closing_iterations(),
            )
        return self._fill_small_mask_holes(repaired, max_hole_area)

    def dilate_inpaint_mask(
        self, mask: Optional[np.ndarray],
    ) -> Optional[np.ndarray]:
        if mask is None:
            return mask
        size = self.mask_dilation_size()
        if size <= 0:
            return mask
        # OpenCV kernels are centered reliably at odd sizes.
        size += 1 - size % 2
        kernel = cv2.getStructuringElement(
            self._kernel_shape(self.mask_dilation_kernel()), (size, size),
        )
        return cv2.dilate(mask, kernel)

    def prepare_inpaint_mask(
        self, mask: Optional[np.ndarray],
    ) -> Optional[np.ndarray]:
        """Repair a mask and then apply its temporary outer expansion once.

        >>> InpainterBase.prepare_inpaint_mask(InpainterBase(), np.zeros((2, 2), np.uint8)).shape
        (2, 2)
        """
        return self.dilate_inpaint_mask(self.repair_inpaint_mask(mask))
    
    def memory_safe_inpaint(self, img: np.ndarray, mask: np.ndarray, textblock_list: List[TextBlock] = None, **kwargs: object) -> np.ndarray:
        '''
        handle cuda out of memory
        '''
        def is_cuda_oom(exc):
            try:
                torch = require_torch()
            except ModuleNotFoundError:
                return False
            return hasattr(torch, 'cuda') and isinstance(exc, torch.cuda.OutOfMemoryError)

        try:
            return self._inpaint(img, mask, textblock_list, **kwargs)
        except Exception as e:
            if is_cuda_oom(e):
                soft_empty_cache()
                try:
                    return self._inpaint(img, mask, textblock_list, **kwargs)
                except Exception as ee:
                    if is_cuda_oom(ee):
                        self.logger.warning(f'CUDA out of memory while calling {self.name}, fall back to cpu...\n\
                                            if running into it frequently, consider lowering the inpaint_size')
                        original_device = None
                        if self.params is not None and 'device' in self.params:
                            original_device = self.get_param_value('device')
                        self.moveToDevice('cpu')
                        inpainted = self._inpaint(img, mask, textblock_list, **kwargs)
                        precision = None
                        if hasattr(self, 'precision'):
                            precision = self.precision
                        if original_device is not None:
                            self.moveToDevice(original_device, precision)

                        return inpainted
            else:
                raise e

    def inpaint(self, img: np.ndarray, mask: np.ndarray, textblock_list: List[TextBlock] = None, check_need_inpaint: bool = False, mask_prepared: bool = False, **kwargs: object) -> np.ndarray:
        """Preserve crop and alpha handling for request-specific module options.

        >>> result = inpainter.inpaint(image, mask, profile=profile)  # doctest: +SKIP
        """
        
        if not self.all_model_loaded():
            self.load_model()
        
        # Handle RGBA images by preserving alpha channel
        original_alpha = None
        if len(img.shape) == 3 and img.shape[2] == 4:
            original_alpha = img[:, :, 3:4]  # Keep alpha channel
            img_rgb = img[:, :, :3]  # Use only RGB for inpainting
        else:
            img_rgb = img

        if mask is not None and not mask_prepared:
            mask = self.prepare_inpaint_mask(mask)

        if pcfg.module.filter_mask_by_bboxes:
            mask = filter_mask_by_bboxes(mask, textblock_list)
        
        if not self.inpaint_by_block or textblock_list is None:
            if check_need_inpaint:
                ballon_msk, non_text_msk = extract_ballon_mask(img_rgb, mask)
                if ballon_msk is not None:
                    non_text_region = np.where(non_text_msk > 0)
                    non_text_px = img_rgb[non_text_region]
                    average_bg_color = np.median(non_text_px, axis=0)
                    std_rgb = np.std(non_text_px - average_bg_color, axis=0)
                    std_max = np.max(std_rgb)
                    inpaint_thresh = 7 if np.std(std_rgb) > 1 else 10
                    if std_max < inpaint_thresh:
                        result_rgb = img_rgb.copy()
                        result_rgb[np.where(ballon_msk > 0)] = average_bg_color
                        # Recombine with alpha if original was RGBA
                        if original_alpha is not None:
                            return np.concatenate([result_rgb, original_alpha], axis=2)
                        return result_rgb
            result_rgb = self.memory_safe_inpaint(img_rgb, mask, textblock_list, **kwargs)
            # Recombine with alpha if original was RGBA
            if original_alpha is not None:
                result_alpha = inpaint_handle_alpha_channel(original_alpha, mask)
                return np.concatenate([result_rgb, result_alpha], axis=2)
            return result_rgb
        else:
            im_h, im_w = img_rgb.shape[:2]
            inpainted = np.copy(img_rgb)
            
            # Preserve original mask for transparency analysis
            original_mask = mask.copy()
            
            for blk in textblock_list:
                xyxy = blk.xyxy
                xyxy_e = enlarge_window(
                    xyxy, im_w, im_h, ratio=self.inpaint_enlarge_ratio(),
                )
                im = inpainted[xyxy_e[1]:xyxy_e[3], xyxy_e[0]:xyxy_e[2]]
                msk = mask[xyxy_e[1]:xyxy_e[3], xyxy_e[0]:xyxy_e[2]]
                need_inpaint = True
                if pcfg.module.check_need_inpaint or check_need_inpaint:
                    ballon_msk, non_text_msk = extract_ballon_mask(im, msk)
                    if ballon_msk is not None:
                        non_text_region = np.where(non_text_msk > 0)
                        non_text_px = im[non_text_region]
                        average_bg_color = np.median(non_text_px, axis=0)
                        std_rgb = np.std(non_text_px - average_bg_color, axis=0)
                        std_max = np.max(std_rgb)
                        inpaint_thresh = 7 if np.std(std_rgb) > 1 else 10
                        if std_max < inpaint_thresh:
                            need_inpaint = False
                            im[np.where(ballon_msk > 0)] = average_bg_color
                        # cv2.imshow('im', im)
                        # cv2.imshow('ballon', ballon_msk)
                        # cv2.imshow('non_text', non_text_msk)
                        # cv2.waitKey(0)
                
                if need_inpaint:
                    inpainted[xyxy_e[1]:xyxy_e[3], xyxy_e[0]:xyxy_e[2]] = self.memory_safe_inpaint(im, msk, **kwargs)

                mask[xyxy[1]:xyxy[3], xyxy[0]:xyxy[2]] = 0
            
            # Recombine with alpha if original was RGBA
            if original_alpha is not None:
                result_alpha = inpaint_handle_alpha_channel(original_alpha, original_mask)
                return np.concatenate([inpainted, result_alpha], axis=2)
            return inpainted

    def _inpaint(self, img: np.ndarray, mask: np.ndarray, textblock_list: List[TextBlock] = None, **kwargs: object) -> np.ndarray:
        raise NotImplementedError
    
    def moveToDevice(self, device: str, precision: str = None):
        raise NotImplementedError
