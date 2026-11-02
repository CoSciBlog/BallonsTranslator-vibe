import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import cv2
import numpy as np
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QApplication

from ballontranslator.glossary import GlossaryWorkspace
from ballontranslator.modules.translators.trans_llm import LLMTranslator
from ballontranslator.ui.translation_benchmark_dialog import (
    TranslationBenchmarkDialog,
    TranslationBenchmarkWorker,
)
from ballontranslator.utils.config import pcfg
from ballontranslator.utils.llm_profiles import LLMProfile
from ballontranslator.utils.proj_imgtrans import ProjImgTrans
from ballontranslator.utils.textblock import TextBlock
from ballontranslator.utils.translation_benchmark import (
    TranslationBenchmarkReport,
    TranslationBenchmarkRun,
    TranslationBenchmarkVariant,
    clone_project_for_benchmark,
)


def _profile(profile_id: str, model: str) -> LLMProfile:
    return LLMProfile(
        id=profile_id,
        name=profile_id.upper(),
        backend='openai',
        base_url='http://127.0.0.1/v1',
        require_api_key=False,
        model=model,
        model_options=[model],
        api_key=f'secret-{profile_id}',
    )


class _Detector:
    name = 'detector'

    def __init__(self) -> None:
        self.calls = 0

    def set_stop_event(self, stop_event) -> None:
        self.stop_event = stop_event

    def detect(self, _image, _project):
        self.calls += 1
        return np.zeros((8, 8), dtype=np.uint8), [
            TextBlock(xyxy=[0, 0, 4, 4]),
            TextBlock(xyxy=[4, 0, 8, 4]),
        ]


class _OCR:
    name = 'ocr'

    def __init__(self) -> None:
        self.calls = 0

    def set_stop_event(self, stop_event) -> None:
        self.stop_event = stop_event

    def run_ocr(self, _image, blocks):
        self.calls += 1
        for index, block in enumerate(blocks, start=1):
            block.text = [f'ocr-{self.calls}-{index}']
        return blocks


class _Translator:
    calls = []

    def __init__(self, source, target, *, profile_override):
        self.source = source
        self.target = target
        self.profile = profile_override

    def set_stop_event(self, stop_event) -> None:
        self.stop_event = stop_event

    def translate_textblk_lst(self, blocks, **_kwargs) -> None:
        self.calls.append(self.profile.id)
        if self.profile.id == 'fail':
            raise RuntimeError('provider echoed secret-fail')
        for block in blocks:
            block.translation = f'{self.profile.model}:{block.get_text()}'

    def on_page_translation_finished(self, _project, _page) -> None:
        pass


class _ModuleManager:
    textdetector = None
    ocr = None

    def prepareTranslationBenchmark(self, on_success, _on_failure) -> None:
        on_success()


class TranslationBenchmarkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory(
            dir=os.environ.get('TEMP') or tempfile.gettempdir(),
        )

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def _project(self, directory: str, page_count: int = 2) -> ProjImgTrans:
        project = ProjImgTrans()
        project.directory = directory
        for index in range(page_count):
            page = f'{index + 1:03d}.png'
            self.assertTrue(cv2.imwrite(
                os.path.join(directory, page),
                np.zeros((8, 8, 3), dtype=np.uint8),
            ))
            project.pages[page] = [
                TextBlock(text=[f'original-{page}'], translation='keep-me')
            ]
            project._pagename2idx[page] = index
            project._idx2pagename[index] = page
            project._image_info[page] = {'finish_code': 0}
        project.current_img = next(iter(project.pages))
        return project

    def test_detection_and_ocr_run_once_before_isolated_variants(self) -> None:
        directory = self.temp_directory.name
        project = self._project(directory)
        detector = _Detector()
        ocr = _OCR()
        variants = [
            TranslationBenchmarkVariant.from_profile(_profile('one', 'm1')),
            TranslationBenchmarkVariant.from_profile(_profile('two', 'm2')),
        ]
        _Translator.calls = []
        worker = TranslationBenchmarkWorker(
            project,
            list(project.pages),
            variants,
            detector,
            ocr,
            '日本語',
            'English',
        )

        with mock.patch(
            'ballontranslator.ui.translation_benchmark_dialog.LLMTranslator',
            _Translator,
        ):
            report = worker.execute()

        self.assertEqual(detector.calls, 2)
        self.assertEqual(ocr.calls, 2)
        self.assertEqual(_Translator.calls, ['one', 'one', 'two', 'two'])
        self.assertEqual(
            report.runs[0].translations['001.png'],
            ['m1:ocr-1-1', 'm1:ocr-1-2'],
        )
        self.assertEqual(
            report.runs[1].translations['002.png'],
            ['m2:ocr-2-1', 'm2:ocr-2-2'],
        )
        self.assertEqual(project.pages['001.png'][0].get_text(), 'original-001.png')
        self.assertEqual(project.pages['001.png'][0].translation, 'keep-me')

    def test_exports_align_blocks_without_api_keys(self) -> None:
        variant = TranslationBenchmarkVariant.from_profile(_profile('one', 'm1'))
        report = TranslationBenchmarkReport(
            pages=['001.png'],
            sources={'001.png': ['A', 'B']},
            source_language='日本語',
            target_language='English',
            text_detector='detector',
            ocr='ocr',
            detection_ocr_seconds=1.0,
            runs=[TranslationBenchmarkRun(
                variant=variant,
                translations={'001.png': ['X', 'Y']},
            )],
        )

        serialized = report.to_dict()
        self.assertNotIn('api_key', str(serialized))
        self.assertNotIn('secret-one', str(serialized))
        self.assertIn('001.png,1,A,X', report.to_csv())

    def test_project_glossary_is_snapshotted_in_memory(self) -> None:
        project = self._project(self.temp_directory.name, page_count=1)
        project.glossary_workspace = GlossaryWorkspace.in_memory()
        project.glossary_service = project.glossary_workspace.project
        project.glossary_service.create_entry(
            original='勇者',
            translation='Hero',
        )

        clone = clone_project_for_benchmark(project)
        self.assertIsNot(clone.glossary_workspace, project.glossary_workspace)
        self.assertIsNone(clone.glossary_service)
        self.assertEqual(
            clone.glossary_workspace.effective_entries()[0].entry.translation,
            'Hero',
        )
        clone.glossary_workspace.project.create_entry(
            original='魔王',
            translation='Demon King',
        )
        self.assertEqual(len(project.glossary_service.entries), 1)

    def test_failed_variant_is_redacted_and_does_not_stop_next_profile(self) -> None:
        project = self._project(self.temp_directory.name, page_count=1)
        variants = [
            TranslationBenchmarkVariant.from_profile(_profile('fail', 'bad')),
            TranslationBenchmarkVariant.from_profile(_profile('good', 'ok')),
        ]
        worker = TranslationBenchmarkWorker(
            project,
            list(project.pages),
            variants,
            _Detector(),
            _OCR(),
            '日本語',
            'English',
        )
        with mock.patch(
            'ballontranslator.ui.translation_benchmark_dialog.LLMTranslator',
            _Translator,
        ):
            report = worker.execute()

        self.assertEqual([run.status for run in report.runs], ['failed', 'completed'])
        self.assertIn('[redacted]', report.runs[0].error)
        self.assertNotIn('secret-fail', str(report.to_dict()))
        self.assertEqual(report.runs[1].translations['001.png'][0], 'ok:ocr-1-1')

    def test_dialog_requires_two_profiles_and_honors_ignored_pages(self) -> None:
        directory = self.temp_directory.name
        project = self._project(directory)
        project._image_info['002.png']['pipeline_ignore'] = True
        profiles = [_profile('one', 'm1'), _profile('two', 'm2')]
        with mock.patch.object(pcfg.module, 'llm_profiles', profiles):
            dialog = TranslationBenchmarkDialog(project, _ModuleManager())
            self.assertEqual(len(dialog.selected_variants()), 2)
            self.assertTrue(dialog.start_button.isEnabled())
            dialog.scope_combo.setCurrentIndex(1)
            self.assertEqual(dialog.selected_pages(), ['001.png'])
            dialog.profile_table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)
            self.assertFalse(dialog.start_button.isEnabled())
            dialog.deleteLater()

    def test_llm_translator_profile_override_is_detached(self) -> None:
        override = _profile('override', 'benchmark-model')
        selected = _profile('selected', 'global-model')
        with mock.patch.object(pcfg.module, 'llm_profiles', [selected]), \
                mock.patch.object(pcfg.module, 'translator_llm_id', selected.id):
            translator = LLMTranslator(
                '日本語',
                'English',
                profile_override=override,
            )
            override.model = 'changed-later'
            self.assertEqual(translator.profile.id, 'override')
            self.assertEqual(translator.profile.model, 'benchmark-model')


if __name__ == '__main__':
    unittest.main()
