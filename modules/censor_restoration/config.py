from dataclasses import dataclass


@dataclass
class CensorRestorationConfig:
    dark_threshold: int = 35
    light_threshold: int = 235
    min_area_ratio: float = 0.00002
    max_area_ratio: float = 0.08
    min_aspect_ratio: float = 2.0
    min_width: int = 8
    min_height: int = 4
    mask_padding: int = 8
    morph_kernel_size: int = 5
    enable_dark_bar_detection: bool = True
    enable_light_bar_detection: bool = True
    merge_nearby_boxes: bool = True
    save_debug_masks: bool = False
    debug_output_dir: str = ""
    allow_blocky_regions: bool = True
    min_block_area_ratio: float = 0.00005
    max_block_area_ratio: float = 0.03
    adaptive_threshold_enabled: bool = True
    merge_distance: int = 12
    ignore_page_border_margin: int = 6
    ignore_very_thin_lines: bool = True
    enable_gray_censor_detection: bool = True
    enable_banded_censor_detection: bool = True
    gray_min_value: int = 70
    gray_max_value: int = 230
    gray_max_saturation: int = 35
    min_gray_rectangularity: float = 0.65
    min_gray_area_ratio: float = 0.00003
    max_gray_area_ratio: float = 0.05
    banded_gradient_threshold: float = 6.0
    min_banded_score: float = 0.16
    ignore_text_inpaint_masks: bool = True
    exclude_text_regions: bool = True
    ignore_thin_panel_lines: bool = True
