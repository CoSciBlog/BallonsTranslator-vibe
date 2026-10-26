import json
import os
import os.path as osp
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from qtpy.QtWidgets import QApplication

import numpy as np

from ballontranslator.utils.io_utils import imread, imwrite
from ballontranslator.utils.batch_processing import BatchOptions, build_batch_tasks
from ballontranslator.utils.config import pcfg
from ballontranslator.utils.proj_imgtrans import ProjImgTrans
from ballontranslator.utils.textblock import TextBlock
from ballontranslator.utils.upscale import (
    stage_upscaled_pages,
    upscale_image,
    upscale_image_2x,
    upscaled_page_name,
)
from ballontranslator.ui.mainwindow import MainWindow, PageListView


class _UpscaleWindow(SimpleNamespace):
    openJsonProj = MainWindow.openJsonProj
    updatePageList = MainWindow.updatePageList
    pageListCurrentItemChanged = MainWindow.pageListCurrentItemChanged


class ProjectUpscaleTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_batch_upscales_ignored_pages_before_filtering_pipeline(self) -> None:
        module_state = {
            key: getattr(pcfg.module, key)
            for key in (
                'enable_detect', 'enable_ocr', 'enable_inpaint',
                'enable_translate', 'finish_code',
            )
        }
        for all_ignored in (False, True):
            with self.subTest(all_ignored=all_ignored), \
                    tempfile.TemporaryDirectory() as directory, \
                    patch.multiple(pcfg.module, **module_state):
                for page_name in ('001.png', '002.png'):
                    imwrite(
                        osp.join(directory, page_name),
                        np.zeros((3, 4, 3), np.uint8), ext='.png',
                    )
                project = ProjImgTrans(directory)
                self.addCleanup(project.close_project_glossary)
                project.set_page_ignored('001.png', True)
                project.set_page_ignored('002.png', all_ignored)
                options = BatchOptions(
                    directory, 'detector', 'ocr', '', 'inpainter', 'translator',
                    upscale_first=True,
                    resume=False,
                )
                owner = SimpleNamespace(
                    imgtrans_proj=project,
                    _batch_options=options,
                    _batch_tasks=build_batch_tasks([directory], options),
                    _batch_task=None,
                    _batch_cancel_requested=False,
                    _batch_failed=False,
                    _history_details=Mock(return_value={}),
                    _start_project_upscale=Mock(),
                    project_upscale_thread=Mock(isRunning=Mock(return_value=True)),
                    _run_current_batch_pipeline=Mock(),
                    on_run_imgtrans=Mock(),
                    _complete_batch_task=Mock(),
                    _finish_batch_processing=Mock(),
                )
                with patch('ballontranslator.ui.mainwindow.QTimer.singleShot') as schedule:
                    MainWindow._run_next_batch_task(owner)

                    owner._start_project_upscale.assert_called_once_with(
                        ['001.png', '002.png']
                    )
                    schedule.assert_not_called()
                    owner._run_current_batch_pipeline.assert_not_called()
                    owner._finish_batch_processing.assert_not_called()

                    owner._batch_task = owner._batch_tasks.pop(0)
                    MainWindow._run_current_batch_pipeline(owner)

                    if all_ignored:
                        owner.on_run_imgtrans.assert_not_called()
                        schedule.assert_called_once_with(0, owner._complete_batch_task)
                    else:
                        owner.on_run_imgtrans.assert_called_once_with(
                            pages_to_process=['002.png']
                        )
                        schedule.assert_not_called()

    def test_batch_upscale_phase_completes_without_starting_pipeline(self) -> None:
        owner = SimpleNamespace(
            _batch_task=SimpleNamespace(phase='upscale'),
            _complete_batch_task=Mock(),
            on_run_imgtrans=Mock(),
        )

        with patch('ballontranslator.ui.mainwindow.QTimer.singleShot') as schedule:
            MainWindow._run_current_batch_pipeline(owner)

        schedule.assert_called_once_with(0, owner._complete_batch_task)
        owner.on_run_imgtrans.assert_not_called()

    def test_batch_resume_dispatches_only_incomplete_pages(self) -> None:
        project = ProjImgTrans()
        project.pages = {'001.png': [], '002.png': [], '003.png': []}
        project._image_info = {
            '001.png': {'finish_code': 15},
            '002.png': {'finish_code': 0},
            '003.png': {'finish_code': 15},
        }
        owner = SimpleNamespace(
            _batch_task=SimpleNamespace(
                project_directory='project',
                phase='complete',
                rerun_inpaint=False,
            ),
            _batch_options=SimpleNamespace(resume=True),
            imgtrans_proj=project,
            on_run_imgtrans=Mock(),
            _complete_batch_task=Mock(),
        )

        with patch('ballontranslator.ui.mainwindow.QTimer.singleShot') as schedule:
            MainWindow._run_current_batch_pipeline(owner)

        owner.on_run_imgtrans.assert_called_once_with(continue_mode=True)
        schedule.assert_not_called()

    def test_batch_resume_completes_task_when_every_page_is_finished(self) -> None:
        project = ProjImgTrans()
        project.pages = {'001.png': [], '002.png': []}
        project._image_info = {
            '001.png': {'finish_code': 15},
            '002.png': {'finish_code': 15},
        }
        owner = SimpleNamespace(
            _batch_task=SimpleNamespace(
                project_directory='project',
                phase='complete',
                rerun_inpaint=False,
            ),
            _batch_options=SimpleNamespace(resume=True),
            imgtrans_proj=project,
            on_run_imgtrans=Mock(),
            _complete_batch_task=Mock(),
        )

        with patch('ballontranslator.ui.mainwindow.QTimer.singleShot') as schedule:
            MainWindow._run_current_batch_pipeline(owner)

        owner.on_run_imgtrans.assert_not_called()
        schedule.assert_called_once_with(0, owner._complete_batch_task)

    def test_batch_can_start_fresh_when_resume_is_disabled(self) -> None:
        project = ProjImgTrans()
        project.pages = {'001.png': []}
        project._image_info = {'001.png': {'finish_code': 15}}
        owner = SimpleNamespace(
            _batch_task=SimpleNamespace(
                project_directory='project',
                phase='complete',
                rerun_inpaint=False,
            ),
            _batch_options=SimpleNamespace(resume=False),
            imgtrans_proj=project,
            on_run_imgtrans=Mock(),
            _complete_batch_task=Mock(),
        )

        with patch('ballontranslator.ui.mainwindow.QTimer.singleShot') as schedule:
            MainWindow._run_current_batch_pipeline(owner)

        owner.on_run_imgtrans.assert_called_once_with(
            pages_to_process=['001.png']
        )
        schedule.assert_not_called()

    def test_batch_upscale_refreshes_pages_before_pipeline_and_navigation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(directory)
            imwrite(
                osp.join(directory, '002.png'),
                np.zeros((3, 4, 3), np.uint8), ext='.png',
            )
            project.pages['002.png'] = []
            project._pagename2idx['002.png'] = 1
            project._idx2pagename[1] = '002.png'
            project.save()
            page_list = PageListView()
            self.addCleanup(page_list.deleteLater)
            owner = _UpscaleWindow(
                imgtrans_proj=project,
                pageList=page_list,
                st_manager=Mock(), canvas=Mock(), llmContextEditor=Mock(),
                leftBar=Mock(), module_manager=Mock(), drawingPanel=Mock(),
                project_upscale_progress=Mock(),
                glossary_window=None, pipeline_history_window=None,
                _batch_upscale_active=True, _batch_cancel_requested=False,
                _batch_failed=False, opening_dir=False, save_on_page_changed=True,
                conditional_save=Mock(), _update_project_title=Mock(),
                _run_current_batch_pipeline=Mock(), _run_next_batch_task=Mock(),
                tr=str,
            )
            page_list.currentItemChanged.connect(owner.pageListCurrentItemChanged)
            owner.openJsonProj(project.proj_path)
            self.assertEqual(page_list.currentItem().text(), '001.png')

            replacements, failures, stopped, staging_dir = stage_upscaled_pages(
                directory, list(project.pages)
            )
            self.addCleanup(shutil.rmtree, staging_dir, True)
            with patch('ballontranslator.ui.mainwindow.QTimer.singleShot') as schedule, \
                    patch('ballontranslator.ui.mainwindow.create_error_dialog') as error_dialog:
                MainWindow.on_project_upscale_finished(
                    owner, replacements, failures, stopped, staging_dir
                )
                error_dialog.assert_not_called()
                schedule.assert_called_once_with(0, owner._run_current_batch_pipeline)
                self.assertEqual(
                    [page_list.item(i).text() for i in range(page_list.count())],
                    ['001_x2.png', '002_x2.png'],
                )
                self.assertEqual(page_list.currentItem().text(), project.current_img)
                self.assertEqual(project.current_img, '001_x2.png')
                self.assertEqual(project.img_array.shape[:2], (6, 8))
                self.assertEqual(project.pages['001_x2.png'][0].xyxy, [2, 4, 6, 8])
                self.assertTrue(project.is_page_ignored('001_x2.png'))
                self.assertEqual(project.pipeline_pages(), ['002_x2.png'])
                self.assertFalse(owner._batch_failed)
                # Pipeline page completions use this same selection signal.
                page_list.setCurrentRow(1)
                self.assertEqual(project.current_img, '002_x2.png')
                self.assertFalse(owner.page_changing)
                self.assertFalse(owner.opening_dir)
                self.assertFalse(osp.exists(staging_dir))

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
