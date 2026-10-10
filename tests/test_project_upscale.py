import json
import os
import os.path as osp
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from ballontranslator.utils.io_utils import imread, imwrite
from ballontranslator.utils.proj_imgtrans import ProjImgTrans
from ballontranslator.utils.textblock import TextBlock
from ballontranslator.utils.upscale import (
    stage_upscaled_pages,
    upscale_image,
    upscale_image_2x,
    upscaled_page_name,
)
from ballontranslator.ui.mainwindow import MainWindow


class ProjectUpscaleTest(unittest.TestCase):

    def test_current_page_and_project_actions_select_expected_pages(self):
        selected = []
        owner = SimpleNamespace(
            imgtrans_proj=SimpleNamespace(
                current_img='002.png',
                pages={'001.png': [], '002.png': []},
            ),
            _run_page_upscale=selected.append,
        )

        MainWindow.run_current_page_upscale(owner)
        MainWindow.run_project_upscale(owner)

        self.assertEqual(
            selected,
            [['002.png'], ['001.png', '002.png']],
        )

    def test_upscale_image_is_exactly_twice_the_source_size(self):
        source = np.zeros((3, 5, 4), dtype=np.uint8)
        source[:, :, 3] = 255

        result = upscale_image_2x(source)

        self.assertEqual(result.shape, (6, 10, 4))

    def test_upscale_name_records_and_combines_factors(self):
        self.assertEqual(upscaled_page_name('001.png', 2), '001_x2.png')
        self.assertEqual(upscaled_page_name('001_x2.png', 2), '001_x4.png')
        self.assertEqual(
            upscaled_page_name('001_upscaled_2x.jpg', 3),
            '001_x6.jpg',
        )
        self.assertEqual(
            upscale_image(np.zeros((2, 3, 3), dtype=np.uint8), 3).shape,
            (6, 9, 3),
        )

    def test_staging_does_not_touch_original_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = osp.join(directory, '001.png')
            source = np.full((3, 4, 3), 90, dtype=np.uint8)
            imwrite(source_path, source, ext='.png')
            original_bytes = Path(source_path).read_bytes()

            replacements, failures, stopped, staging_dir = (
                stage_upscaled_pages(directory, ['001.png'])
            )
            self.addCleanup(shutil.rmtree, staging_dir, True)

            self.assertFalse(failures)
            self.assertFalse(stopped)
            self.assertEqual(Path(source_path).read_bytes(), original_bytes)
            self.assertEqual(replacements[0]['target_name'], '001_x2.png')
            self.assertEqual(
                imread(replacements[0]['staged_path']).shape[:2],
                (6, 8),
            )

    def test_one_staging_failure_prevents_every_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = osp.join(directory, '001.png')
            source = np.full((3, 4, 3), 90, dtype=np.uint8)
            imwrite(source_path, source, ext='.png')
            original_bytes = Path(source_path).read_bytes()

            with patch(
                'ballontranslator.utils.upscale.LOGGER.exception'
            ):
                replacements, failures, stopped, staging_dir = (
                    stage_upscaled_pages(
                        directory,
                        ['001.png', 'missing.png'],
                    )
                )

            self.assertEqual(replacements, [])
            self.assertEqual(failures[0][0], 'missing.png')
            self.assertFalse(stopped)
            self.assertEqual(staging_dir, '')
            self.assertEqual(Path(source_path).read_bytes(), original_bytes)

    def test_activation_replaces_image_and_scales_project_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(directory)
            mask_path = project.get_mask_path('001.png')
            result_path = project.get_result_path('001.png')
            imwrite(mask_path, np.zeros((3, 4), dtype=np.uint8), ext='.png')
            imwrite(result_path, np.zeros((3, 4, 3), dtype=np.uint8), ext='.png')
            project.save()
            replacements, failures, stopped, staging_dir = (
                stage_upscaled_pages(directory, ['001.png'])
            )
            self.addCleanup(shutil.rmtree, staging_dir, True)

            project.replace_pages_with_upscaled_files(replacements)

            self.assertFalse(failures)
            self.assertFalse(stopped)
            target_path = osp.join(directory, '001_x2.png')
            self.assertFalse(osp.exists(osp.join(directory, '001.png')))
            self.assertEqual(imread(target_path).shape[:2], (6, 8))
            self.assertNotIn('001.png', project.pages)
            block = project.pages['001_x2.png'][0]
            self.assertEqual(block.xyxy, [2, 4, 6, 8])
            self.assertEqual(block.lines[0][0], [2, 4])
            self.assertEqual(block.font_size, 24)
            self.assertEqual(project._image_info['001_x2.png']['finish_code'], 0)
            self.assertTrue(project.is_page_ignored('001_x2.png'))
            self.assertFalse(osp.exists(mask_path))
            self.assertFalse(osp.exists(result_path))
            with open(project.proj_path, encoding='utf-8') as project_file:
                persisted = json.load(project_file)
            self.assertEqual(
                persisted['image_info']['001_x2.png']['width'],
                8,
            )
            self.assertIn('001_x2.png', persisted['pages'])
            self.assertEqual(persisted['current_img'], '001_x2.png')

    def test_repeated_activation_uses_cumulative_factor_name(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(directory)
            replacements, _, _, staging_dir = stage_upscaled_pages(
                directory, ['001.png']
            )
            self.addCleanup(shutil.rmtree, staging_dir, True)
            project.replace_pages_with_upscaled_files(replacements)

            replacements, _, _, staging_dir = stage_upscaled_pages(
                directory, ['001_x2.png']
            )
            self.addCleanup(shutil.rmtree, staging_dir, True)
            project.replace_pages_with_upscaled_files(replacements)

            self.assertEqual(list(project.pages), ['001_x4.png'])
            self.assertTrue(osp.isfile(osp.join(directory, '001_x4.png')))
            self.assertFalse(osp.exists(osp.join(directory, '001_x2.png')))
            self.assertEqual(
                imread(osp.join(directory, '001_x4.png')).shape[:2],
                (12, 16),
            )

    def test_activation_restores_original_file_and_geometry_on_save_error(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(directory)
            source_path = osp.join(directory, '001.png')
            original_bytes = Path(source_path).read_bytes()
            replacements, _, _, staging_dir = stage_upscaled_pages(
                directory,
                ['001.png'],
            )
            self.addCleanup(shutil.rmtree, staging_dir, True)

            with patch.object(project, 'save', side_effect=OSError('disk full')):
                with self.assertRaisesRegex(OSError, 'disk full'):
                    project.replace_pages_with_upscaled_files(replacements)

            self.assertEqual(Path(source_path).read_bytes(), original_bytes)
            self.assertEqual(project.pages['001.png'][0].xyxy, [1, 2, 3, 4])
            self.assertEqual(project.pages['001.png'][0].font_size, 12)
            self.assertEqual(project._image_info['001.png']['finish_code'], 15)

    @staticmethod
    def _project(directory: str) -> ProjImgTrans:
        source = np.full((3, 4, 3), 90, dtype=np.uint8)
        imwrite(osp.join(directory, '001.png'), source, ext='.png')
        block = TextBlock(
            xyxy=[1, 2, 3, 4],
            lines=[[[1, 2], [3, 2], [3, 4], [1, 4]]],
        )
        block.font_size = 12
        project = ProjImgTrans()
        project.directory = directory
        project.proj_path = osp.join(directory, 'imgtrans_test.json')
        project.pages = {'001.png': [block]}
        project._pagename2idx = {'001.png': 0}
        project._idx2pagename = {0: '001.png'}
        project.current_img = '001.png'
        project._image_info = {
            '001.png': {
                'finish_code': 15,
                'pipeline_ignore': True,
            },
        }
        return project


if __name__ == '__main__':
    unittest.main()
