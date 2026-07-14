import unittest
from unittest.mock import Mock, patch

from modules.ocr.ocr_manga import MangaOcr


class MangaOcrGenerationTests(unittest.TestCase):
    @patch('modules.ocr.ocr_manga.VisionEncoderDecoderModel.from_pretrained')
    @patch('modules.ocr.ocr_manga.AutoTokenizer.from_pretrained')
    @patch('modules.ocr.ocr_manga.AutoImageProcessor.from_pretrained')
    def test_legacy_max_length_is_disabled(
        self,
        image_processor_from_pretrained,
        tokenizer_from_pretrained,
        model_from_pretrained,
    ):
        model = Mock()
        model.generation_config.max_length = 300
        model_from_pretrained.return_value = model

        manga_ocr = MangaOcr(device='cpu')

        self.assertIsNone(manga_ocr.model.generation_config.max_length)
        model.to.assert_called_once_with('cpu')


if __name__ == '__main__':
    unittest.main()
