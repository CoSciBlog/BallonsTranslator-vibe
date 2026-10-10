import unittest
import weakref
from unittest.mock import patch

from ballontranslator.modules import base
from ballontranslator.modules.base import BaseModule
from ballontranslator.modules.exceptions import LLMUserActionRequiredError
from ballontranslator.modules.llm_chat import LLMChatRequester
from ballontranslator.modules.llm_image import LLMImageRequester
from ballontranslator.utils.config import ModuleConfig, pcfg
from ballontranslator.utils.llm_profiles import LLMProfile


class _ResidentModule(BaseModule):
    _load_model_keys = {'model'}

    def _load_model(self) -> None:
        self.model = object()


class LLMModelMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_setting = pcfg.module.unload_models_before_llm

    def tearDown(self) -> None:
        pcfg.module.unload_models_before_llm = self.original_setting

    def test_disabled_setting_keeps_loaded_models(self) -> None:
        module = _ResidentModule()
        module.load_model()
        pcfg.module.unload_models_before_llm = False

        with patch.object(
            base,
            '_LIVE_MODULES',
            weakref.WeakValueDictionary({id(module): module}),
        ), \
                patch.object(base, 'soft_empty_cache') as empty_cache:
            released = base.unload_models_before_llm_request()

        self.assertEqual(released, 0)
        self.assertTrue(module.all_model_loaded())
        empty_cache.assert_not_called()

    def test_enabled_setting_unloads_models_but_retains_requester(self) -> None:
        requester = _ResidentModule()
        other = _ResidentModule()
        requester.load_model()
        other.load_model()
        pcfg.module.unload_models_before_llm = True

        with patch.object(
            base,
            '_LIVE_MODULES',
            weakref.WeakValueDictionary({
                id(requester): requester,
                id(other): other,
            }),
        ), patch.object(base, 'soft_empty_cache') as empty_cache:
            released = base.unload_models_before_llm_request(requester)

        self.assertEqual(released, 1)
        self.assertTrue(requester.all_model_loaded())
        self.assertFalse(other.all_model_loaded())
        empty_cache.assert_called_once_with()

    def test_invalid_saved_setting_returns_to_safe_default(self) -> None:
        config = ModuleConfig(unload_models_before_llm='yes')

        self.assertFalse(config.unload_models_before_llm)

    def test_chat_request_releases_models_before_provider_dispatch(self) -> None:
        requester = LLMChatRequester()
        profile = LLMProfile(backend='unavailable')

        with patch(
            'ballontranslator.modules.llm_chat.unload_models_before_llm_request'
        ) as unload:
            with self.assertRaises(LLMUserActionRequiredError):
                requester.request_chat_completion(profile, {'model': 'test'})

        unload.assert_called_once_with(requester)

    def test_image_request_releases_models_before_client_creation(self) -> None:
        requester = LLMImageRequester()
        profile = LLMProfile(
            backend='openai',
            image_model='test-image',
            image_model_options=['test-image'],
        )

        with patch(
            'ballontranslator.modules.llm_image.unload_models_before_llm_request'
        ) as unload, patch.object(
            requester,
            '_initialize_client',
            side_effect=RuntimeError('client creation stopped'),
        ):
            with self.assertRaisesRegex(RuntimeError, 'client creation stopped'):
                requester.request_image(profile, None)

        unload.assert_called_once_with(requester)


if __name__ == '__main__':
    unittest.main()
