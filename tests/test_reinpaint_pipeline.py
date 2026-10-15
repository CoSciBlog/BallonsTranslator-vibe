import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from unittest.mock import patch

import numpy as np
import pytest
from qtpy.QtCore import QThread
from qtpy.QtWidgets import QApplication

from ballontranslator.modules.inpaint.base import InpainterBase
from ballontranslator.ui import module_manager as M
from ballontranslator.utils.config import RunStatus, pcfg
from ballontranslator.utils.io_utils import imwrite
from ballontranslator.utils.proj_imgtrans import ProjImgTrans
from ballontranslator.utils.textblock import TextBlock


@pytest.mark.parametrize('optimize', [False, True])
def test_reinpaint_prepares_detector_only_when_optimization_is_enabled(tmp_path, monkeypatch, optimize):
    app = QApplication.instance() or QApplication([])
    imwrite(str(tmp_path / '001.png'), np.full((9, 10, 3), 255, np.uint8))
    project = ProjImgTrans(str(tmp_path))
    manager = M.ModuleManager(project)
    monkeypatch.setattr(pcfg.module, 'enable_inpaint_optimization', optimize)
    with patch.object(manager, 'terminateRunningThread'), patch.object(manager, '_prepare_modules_then') as prepare:
        manager.runReinpaintPipeline(['001.png'])
    prepared_keys = [key for key, _ in prepare.call_args.args[0]]
    assert prepared_keys == (['textdetector', 'inpainter'] if optimize else ['inpainter'])
    project.close_project_glossary()
    manager.deleteLater()
    app.processEvents()


def test_reinpaint_worker_repairs_and_reloads_real_project_files(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(pcfg, 'intermediate_imgsave_ext', '.png')
    monkeypatch.setattr(pcfg.module, 'enable_inpaint_optimization', True)
    monkeypatch.setattr(pcfg.module, 'filter_mask_by_bboxes', True)
    monkeypatch.setattr(pcfg.drawpanel, 'reinpaint_dilate_ksize', 1)
    source = np.full((9, 10, 3), 255, np.uint8)
    source[2, 2] = source[6, 7] = 0
    imwrite(str(tmp_path / '001.png'), source)
    project = ProjImgTrans(str(tmp_path))
    block = TextBlock(xyxy=[1, 1, 3, 3], text=['keep OCR'], translation='keep translation')
    project.pages['001.png'] = [block]
    project.current_img = '001.png'
    mask = np.zeros(source.shape[:2], np.uint8)
    mask[2, 2] = mask[0, 9] = 255
    project.save_mask('001.png', mask)
    calls = []

    class Painter(InpainterBase):
        def all_model_loaded(self) -> bool:
            return True

        def _inpaint(self, image, inpaint_mask, textblock_list=None, **kwargs):
            calls.append((QThread.currentThread(), image.copy(), inpaint_mask.copy(), textblock_list))
            result = image.copy()
            result[inpaint_mask > 0] = 255
            return result

    class Detector:
        def detect(self, image, proj):
            assert QThread.currentThread() != app.thread()
            assert image[2, 2, 0] == 255
            residual = np.zeros(image.shape[:2], np.uint8)
            residual[image[..., 0] == 0] = 255
            return residual, [TextBlock(xyxy=[6, 5, 9, 8], text=['residual'])]

    workers = [M.TextDetectThread(), M.OCRThread(), M.TranslateThread(), M.InpaintThread()]
    workers[0].module = Detector()
    workers[3].module = Painter()
    pipeline = M.ImgtransThread(*workers)
    try:
        pipeline.runReinpaintPipeline(project, ['001.png'])
        assert pipeline.wait(5000), 'Re-inpaint worker did not finish'
        assert not pipeline.isStopRequested()
        assert pipeline.inpaint_counter == 1
        assert len(calls) == 2
        assert all(thread != app.thread() and blocks is None for thread, _, _, blocks in calls)
        np.testing.assert_array_equal(calls[0][1], source)
        assert calls[1][1][2, 2, 0] == 255
        assert calls[1][1][6, 7, 0] == 0
        np.testing.assert_array_equal(project.read_img('001.png'), source)
        saved_mask = project.load_mask_by_imgname('001.png')
        assert saved_mask[6, 7] == saved_mask[0, 9] == saved_mask[1, 2] == 255
        np.testing.assert_array_equal(project.mask_array, saved_mask)
        assert np.all(project.load_inpainted_by_imgname('001.png') == 255)
        assert project.pages['001.png'] == [block]
        assert block.get_text() == 'keep OCR'
        assert block.translation == 'keep translation'
        assert project._image_info['001.png']['finish_code'] & RunStatus.FIN_INPAINT
    finally:
        pipeline.requestStop()
        pipeline.wait(5000)
        project.close_project_glossary()
        pipeline.deleteLater()
        for worker in workers:
            worker.deleteLater()
        app.processEvents()
