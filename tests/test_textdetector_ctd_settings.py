import copy
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from qtpy.QtCore import QCoreApplication, QEvent
from qtpy.QtWidgets import QApplication

from ballontranslator.modules.textdetector.detector_ctd import (
    ComicTextDetector,
    load_ctd_model,
)
from ballontranslator.modules.textdetector.ctd import inference as ctd_inference
from ballontranslator.modules.base import patch_module_params
from ballontranslator.ui.module_parse_widgets import ParamWidget


class ComicTextDetectorSettingsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self) -> None:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        super().tearDown()

    def setUp(self) -> None:
        ComicTextDetector.params['confidence threshold']['value'] = 0.4
        ComicTextDetector.params['NMS threshold']['value'] = 0.35
        ComicTextDetector.params['half precision']['value'] = False
        super().setUp()

    def test_detect_sizes_extend_to_stride_compatible_2496(self) -> None:
        sizes = ComicTextDetector.params['detect_size']['options']

        self.assertEqual(sizes[:4], [896, 1024, 1152, 1280])
        self.assertEqual(sizes[-1], 2496)
        self.assertIn(2048, sizes)
        self.assertTrue(all(size <= 2500 and size % 64 == 0 for size in sizes))

    def test_all_visible_parameters_have_labels_and_descriptions(self) -> None:
        visible_params = {
            key: value
            for key, value in ComicTextDetector.params.items()
            if key != 'description' and not key.startswith('__')
        }

        for key, param in visible_params.items():
            with self.subTest(parameter=key):
                self.assertIsInstance(param, dict)
                self.assertTrue(param.get('display_name'))
                self.assertTrue(param.get('description'))

    def test_parameter_explanations_reach_editors_and_labels(self) -> None:
        widget = ParamWidget(
            copy.deepcopy(ComicTextDetector.params),
            module_type='textdetector',
            module_key='ctd',
            spaced_fields=True,
        )
        self.addCleanup(widget.deleteLater)

        for key, editor in widget.param_widgets.items():
            with self.subTest(parameter=key):
                self.assertTrue(editor.toolTip())
                self.assertTrue(widget.param_rows[key][0].toolTip())

    def test_loader_forwards_split_batch_limit(self) -> None:
        with patch(
            'ballontranslator.modules.textdetector.detector_ctd.CTDModel'
        ) as model_class:
            load_ctd_model('model.pt', 'cuda', 2048, 8)

        model_class.assert_called_once_with(
            'model.pt',
            detect_size=2048,
            device='cuda',
            det_rearrange_max_batches=8,
            half=False,
            nms_thresh=0.35,
            conf_thresh=0.4,
        )

    def test_quality_controls_are_exposed_with_compatible_defaults(self) -> None:
        self.assertEqual(
            ComicTextDetector.params['confidence threshold']['value'], 0.4
        )
        self.assertEqual(ComicTextDetector.params['NMS threshold']['value'], 0.35)
        self.assertFalse(ComicTextDetector.params['half precision']['value'])

    def test_legacy_plain_values_survive_parameter_metadata_upgrade(self) -> None:
        legacy = {
            'confidence threshold': 0.55,
            'NMS threshold': 0.25,
            'half precision': True,
            'font size multiplier': 1.25,
            'font size max': 72,
            'font size min': 10,
            'mask dilate size': 5,
        }

        patched = patch_module_params(
            legacy,
            copy.deepcopy(ComicTextDetector.params),
            'ctd',
        )

        self.assertEqual(patched['font size multiplier']['value'], 1.25)
        self.assertEqual(patched['font size max']['value'], 72)
        self.assertEqual(patched['font size min']['value'], 10)
        self.assertEqual(patched['mask dilate size']['value'], 5)
        self.assertEqual(patched['confidence threshold']['value'], 0.55)
        self.assertEqual(patched['NMS threshold']['value'], 0.25)
        self.assertTrue(patched['half precision']['value'])

    def test_loaded_model_receives_runtime_size_and_batch_changes(self) -> None:
        detector = ComicTextDetector(
            **copy.deepcopy(ComicTextDetector.params)
        )
        detector.model = SimpleNamespace(
            device='cuda',
            detect_size=1280,
            det_rearrange_max_batches=4,
            conf_thresh=0.4,
            nms_thresh=0.35,
        )

        detector.updateParam('detect_size', '2048')
        detector.updateParam('det_rearrange_max_batches', '8')
        detector.updateParam('confidence threshold', '0.6')
        detector.updateParam('NMS threshold', '0.2')

        self.assertEqual(detector.model.detect_size, 2048)
        self.assertEqual(detector.model.det_rearrange_max_batches, 8)
        self.assertEqual(detector.model.conf_thresh, 0.6)
        self.assertEqual(detector.model.nms_thresh, 0.2)

    def test_half_precision_change_reloads_a_loaded_model(self) -> None:
        detector = ComicTextDetector(**copy.deepcopy(ComicTextDetector.params))
        detector.model = SimpleNamespace(device='cuda')

        with patch.object(detector, 'unload_model') as unload, patch.object(
            detector, 'load_model'
        ) as load:
            detector.updateParam('half precision', True)

        unload.assert_called_once_with()
        load.assert_called_once_with()

    def test_half_precision_is_used_for_rearranged_batches(self) -> None:
        import torch

        seen = []

        class FakeTorchModel:
            def __call__(self, batch):
                seen.append(batch.dtype)
                return (
                    None,
                    torch.zeros((1, 1), dtype=batch.dtype),
                    torch.zeros((1, 1), dtype=batch.dtype),
                )

        detector = ctd_inference.TextDetector.__new__(ctd_inference.TextDetector)
        detector.net = FakeTorchModel()
        detector.half = True
        with patch.object(ctd_inference, 'TextDetBase', FakeTorchModel):
            detector.det_batch_forward_ctd(
                np.zeros((1, 8, 8, 3), dtype=np.uint8), 'cpu'
            )

        self.assertEqual(seen, [torch.float16])


if __name__ == '__main__':
    unittest.main()
