import unittest

from utils.config import ModuleConfig
from utils.ocr_language import canonical_ocr_language, ocr_languages_compatible


class PipelineOrderConfigTest(unittest.TestCase):
    def test_old_configs_default_to_overlapped_translation(self):
        config = ModuleConfig(enable_translate=True)

        self.assertFalse(config.translate_after_image_processing)

    def test_deferred_translation_setting_is_serialized(self):
        config = ModuleConfig(translate_after_image_processing=True)

        saved = config.get_saving_params()

        self.assertTrue(saved['translate_after_image_processing'])

    def test_pipeline_completion_notification_defaults_off_and_is_serialized(self):
        self.assertFalse(ModuleConfig().pipeline_completion_notification)

        saved = ModuleConfig(
            pipeline_completion_notification=True
        ).get_saving_params()

        self.assertTrue(saved['pipeline_completion_notification'])

    def test_ocr_fallback_defaults_and_settings_are_serialized(self):
        config = ModuleConfig()
        self.assertFalse(config.ocr_fallback_enabled)
        self.assertTrue(config.ocr_fallback_on_empty)
        self.assertTrue(config.ocr_fallback_on_failure)

        saved = ModuleConfig(
            ocr_fallback_enabled=True,
            ocr_fallback='windows_ocr',
            ocr_fallback_on_empty=False,
        ).get_saving_params()

        self.assertTrue(saved['ocr_fallback_enabled'])
        self.assertEqual(saved['ocr_fallback'], 'windows_ocr')
        self.assertFalse(saved['ocr_fallback_on_empty'])

    def test_ocr_language_compatibility_accepts_names_and_locale_codes(self):
        self.assertEqual(canonical_ocr_language('German'), 'de')
        self.assertTrue(ocr_languages_compatible('Japanese', 'ja-JP'))
        self.assertTrue(ocr_languages_compatible('English', 'auto'))
        self.assertFalse(ocr_languages_compatible('Japanese', 'English'))


if __name__ == '__main__':
    unittest.main()
