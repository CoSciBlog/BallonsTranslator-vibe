import unittest

from utils.config import ModuleConfig


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


if __name__ == '__main__':
    unittest.main()
