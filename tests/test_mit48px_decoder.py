import unittest
from types import SimpleNamespace

from ballontranslator.modules.ocr.mit48px import OCR


class Mit48pxDecoderCompatibilityTests(unittest.TestCase):
    def test_legacy_beam_entry_point_uses_tensorized_decoder(self):
        calls = []

        def infer_beam_batch_tensor(image, widths, **kwargs):
            calls.append((image, widths, kwargs))
            return ['decoded']

        decoder = SimpleNamespace(infer_beam_batch_tensor=infer_beam_batch_tensor)
        result = OCR.infer_beam_batch(
            decoder,
            'image',
            [128],
            beams_k=3,
            max_seq_length=64,
        )

        self.assertEqual(result, ['decoded'])
        self.assertEqual(calls[0][0:2], ('image', [128]))
        self.assertEqual(calls[0][2]['beams_k'], 3)
        self.assertEqual(calls[0][2]['max_seq_length'], 64)


if __name__ == '__main__':
    unittest.main()
