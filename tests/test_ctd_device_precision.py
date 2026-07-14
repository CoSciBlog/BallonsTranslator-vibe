import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from modules.textdetector.ctd import basemodel, inference


class _FakeModel:
    def __init__(self):
        self.calls = []

    def load_state_dict(self, state):
        self.calls.append(("load_state_dict", state))
        return self

    def eval(self):
        self.calls.append(("eval",))
        return self

    def to(self, device):
        self.calls.append(("to", device))
        return self

    def half(self):
        self.calls.append(("half",))
        return self


class ComicTextDetectorDevicePrecisionTest(unittest.TestCase):
    def test_half_precision_models_move_to_device_before_conversion(self):
        models = [_FakeModel(), _FakeModel(), _FakeModel()]
        checkpoint = {"blk_det": object(), "text_seg": {}, "text_det": {}}

        with patch.object(basemodel.torch, "load", return_value=checkpoint), \
             patch.object(basemodel, "load_yolov5_ckpt", return_value=models[0]), \
             patch.object(basemodel, "UnetHead", return_value=models[1]), \
             patch.object(basemodel, "DBHead", return_value=models[2]):
            result = basemodel.get_base_det_models("unused.pt", device="cuda:0", half=True)

        self.assertEqual(result, tuple(models))
        for model in models:
            self.assertLess(model.calls.index(("to", "cuda:0")), model.calls.index(("half",)))

    def test_rearranged_batches_match_half_precision_model(self):
        detector = object.__new__(inference.TextDetector)
        detector.net = MagicMock(spec=inference.TextDetBase)
        mask = MagicMock()
        mask.cpu.return_value.numpy.return_value = np.zeros((1, 1))
        lines = MagicMock()
        lines.cpu.return_value.numpy.return_value = np.zeros((1, 1))
        detector.net.return_value = (None, mask, lines)
        detector.half = True
        tensor = MagicMock()
        tensor.to.return_value = tensor
        tensor.half.return_value = tensor

        with patch.object(inference.torch, "from_numpy", return_value=tensor):
            detector.det_batch_forward_ctd(np.zeros((1, 8, 8, 3), dtype=np.uint8), "cuda:0")

        tensor.to.assert_called_once_with("cuda:0")
        tensor.half.assert_called_once_with()
        detector.net.assert_called_once_with(tensor)

    def test_device_change_is_retained_when_model_is_reloaded(self):
        detector = object.__new__(inference.TextDetector)
        detector.device = "cuda:0"
        detector.half = True
        detector.load_model = MagicMock()

        with patch.object(inference.osp, "exists", return_value=True):
            detector.set_device("cpu")

        self.assertEqual(detector.device, "cpu")
        self.assertTrue(detector.half)
        detector.load_model.assert_called_once_with(inference.CTD_MODEL_PATH + ".onnx")


if __name__ == "__main__":
    unittest.main()
