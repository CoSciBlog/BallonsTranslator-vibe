import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from ballontranslator.utils.config import ProgramConfig, pcfg
from ballontranslator.utils.io_utils import imread
from ballontranslator.utils.proj_imgtrans import (
    INTERMEDIATE_IMAGE_EXTENSIONS,
    ProjImgTrans,
    get_last_modified_file,
)


class ImageIOTest(unittest.TestCase):
    def test_imread_normalizes_16_bit_grayscale_png_to_uint8_rgb(self):
        source = np.array(
            [[0, 256], [32768, 65535]],
            dtype=np.uint16,
        )
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / 'gray16.png'
            Image.fromarray(source).save(image_path)

            loaded = imread(str(image_path))

        self.assertEqual(loaded.dtype, np.uint8)
        self.assertEqual(loaded.shape, (2, 2, 3))
        np.testing.assert_array_equal(
            loaded[:, :, 0],
            np.array([[0, 1], [128, 255]], dtype=np.uint8),
        )
        np.testing.assert_array_equal(loaded[:, :, 0], loaded[:, :, 1])
        np.testing.assert_array_equal(loaded[:, :, 1], loaded[:, :, 2])

    def test_intermediate_save_uses_configured_format_and_quality(self):
        project = ProjImgTrans()
        mask = np.zeros((2, 2), dtype=np.uint8)
        inpainted = np.zeros((2, 2, 3), dtype=np.uint8)

        with (
            patch.object(pcfg, 'intermediate_imgsave_ext', '.webp'),
            patch.object(pcfg, 'intermediate_imgsave_quality', 82),
            patch.object(project, 'get_mask_path', return_value='mask.png'),
            patch.object(project, 'get_inpainted_path', return_value='inpainted.png'),
            patch('ballontranslator.utils.proj_imgtrans.imwrite') as mocked_write,
        ):
            project.save_mask('page.png', mask)
            project.save_inpainted('page.png', inpainted)

        self.assertEqual(
            mocked_write.call_args_list[0].kwargs,
            {'ext': '.webp', 'quality': 82},
        )
        self.assertEqual(
            mocked_write.call_args_list[1].kwargs,
            {'ext': '.webp', 'quality': 82},
        )

    def test_intermediate_lookup_includes_jpg_and_webp(self):
        self.assertIn('.jpg', INTERMEDIATE_IMAGE_EXTENSIONS)
        self.assertIn('.webp', INTERMEDIATE_IMAGE_EXTENSIONS)

        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / 'page'
            jpg_path = prefix.with_suffix('.jpg')
            webp_path = prefix.with_suffix('.webp')
            jpg_path.touch()
            webp_path.touch()
            os.utime(webp_path, (100, 100))
            os.utime(jpg_path, (200, 200))

            found = get_last_modified_file(
                str(prefix),
                INTERMEDIATE_IMAGE_EXTENSIONS,
            )

        self.assertEqual(found, str(jpg_path))

    def test_invalid_intermediate_image_settings_fall_back_safely(self):
        config = ProgramConfig(
            intermediate_imgsave_ext='.bmp',
            intermediate_imgsave_quality='maximum',
        )

        self.assertEqual(config.intermediate_imgsave_ext, '.png')
        self.assertEqual(config.intermediate_imgsave_quality, 100)


if __name__ == '__main__':
    unittest.main()
