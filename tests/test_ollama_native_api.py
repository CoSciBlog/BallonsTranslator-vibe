import os.path as osp
import sys
import unittest
from types import SimpleNamespace


APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from modules.translators.trans_llm_api import (
    GlossaryResponse,
    LLM_API_Translator,
    LLM_API_Translator_2,
)
from modules.translators.trans_two_step import TwoStepTranslator
from utils.ollama import (
    OLLAMA_DEFAULT_ENDPOINT,
    ollama_chat_endpoint,
    ollama_tags_endpoint,
)


class FakeResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "message": {"content": '{"translations":[{"id":1,"translation":"Hello"}]}'},
            "prompt_eval_count": 7,
            "prompt_eval_duration": 100_000_000,
            "eval_count": 5,
            "eval_duration": 250_000_000,
            "total_duration": 500_000_000,
            "load_duration": 50_000_000,
        }


class FakeHttpClient:
    def __init__(self):
        self.requests = []

    def post(self, url, json, timeout):
        self.requests.append((url, json, timeout))
        return FakeResponse()


class FakeLogger:
    def __init__(self):
        self.infos = []
        self.warnings = []

    def info(self, message):
        self.infos.append(message)

    def warning(self, message):
        self.warnings.append(message)

    def debug(self, _message):
        return None

    def error(self, _message):
        return None


class NativeOllamaTranslator(LLM_API_Translator):
    def __init__(self, endpoint="http://localhost:11434/v1"):
        self.client = FakeHttpClient()
        self.logger = FakeLogger()
        self._params = {
            "provider": "Ollama",
            "endpoint": endpoint,
            "temperature": 0.1,
            "top p": 1.0,
            "max tokens": 4096,
            "request timeout": 300,
            "num ctx": 0,
            "reasoning": False,
            "reasoning level": "medium",
        }

    def get_param_value(self, param_key):
        return self._params.get(param_key)


class StructuredFallbackTranslator(NativeOllamaTranslator):
    def __init__(self, responses):
        super().__init__()
        self.responses = list(responses)
        self.request_args = []
        self.token_count = 0
        self.token_count_last = 0
        self.lang_source = "Japanese"
        self.lang_target = "English"
        self.lang_map = {"Japanese": "Japanese", "English": "English"}
        self._params.update(
            {
                "model": "gemma4:12b",
                "override model": "",
                "system_prompt": "Return only the requested JSON object.",
                "request prompt": "",
                "json mode": True,
                "reasoning": True,
                "reflection": False,
                "num ctx": 24576,
            }
        )

    def _select_api_key(self):
        return "dummy-key"

    def _initialize_client(self, _api_key):
        return True

    def _respect_delay(self):
        return None

    def _create_completion(self, api_args):
        self.request_args.append(api_args)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.responses.pop(0))
                )
            ],
            usage=SimpleNamespace(total_tokens=10),
        )


class NativeOllamaTransportTest(unittest.TestCase):
    def test_thought_json_retries_translation_once_without_thinking(self):
        translator = StructuredFallbackTranslator(
            [
                '{"thought_process":"Translate the supplied text."}',
                '{"translations":[{"id":1,"translation":"Hello"}]}',
            ]
        )

        response = translator._request_translation("Translate item 1.")

        self.assertEqual(response.translations[0].translation, "Hello")
        self.assertTrue(translator.request_args[0]["extra_body"]["think"])
        self.assertFalse(translator.request_args[1]["extra_body"]["think"])
        self.assertEqual(len(translator.request_args), 2)
        self.assertIn("retrying this request once", translator.logger.warnings[-1])

    def test_thought_json_retries_glossary_once_without_thinking(self):
        translator = StructuredFallbackTranslator(
            [
                '{"thought_process_not_included":"none"}',
                '{"entries":[]}',
            ]
        )

        response = translator._request_model_object(
            "Extract glossary entries.",
            GlossaryResponse,
            "Return GlossaryResponse JSON.",
            purpose="glossary",
        )

        self.assertEqual(response.entries, [])
        self.assertTrue(translator.request_args[0]["extra_body"]["think"])
        self.assertFalse(translator.request_args[1]["extra_body"]["think"])
        self.assertEqual(len(translator.request_args), 2)

    def test_ollama_chat_request_uses_native_payload_and_context_option(self):
        translator = NativeOllamaTranslator()

        completion = translator._create_completion(
            {
                "model": "translategemma:12b",
                "messages": [{"role": "user", "content": "Translate."}],
                "temperature": 0.2,
                "top_p": 0.9,
                "max_tokens": 2048,
                "response_format": {"type": "json_object"},
                "extra_body": {"num_ctx": 8192, "think": False},
            }
        )

        url, payload, timeout = translator.client.requests[0]
        self.assertEqual(url, "http://localhost:11434/api/chat")
        self.assertEqual(payload["format"], "json")
        self.assertFalse(payload["stream"])
        self.assertFalse(payload["think"])
        self.assertEqual(payload["options"]["num_ctx"], 8192)
        self.assertEqual(payload["options"]["num_predict"], 2048)
        self.assertEqual(payload["options"]["temperature"], 0.2)
        self.assertEqual(payload["options"]["top_p"], 0.9)
        self.assertEqual(timeout, 300)
        self.assertEqual(completion.usage.total_tokens, 12)
        self.assertIn('"Hello"', completion.choices[0].message.content)
        self.assertIn("prompt=7 tokens at 70.00 tkn/s", translator.logger.infos[0])
        self.assertIn("output=5 tokens at 20.00 tkn/s", translator.logger.infos[0])

    def test_ollama_chat_request_uses_configured_request_timeout(self):
        translator = NativeOllamaTranslator()
        translator._params["request timeout"] = 600

        translator._create_completion(
            {
                "model": "hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M",
                "messages": [{"role": "user", "content": "Translate."}],
            }
        )

        _, _, timeout = translator.client.requests[0]
        self.assertEqual(timeout, 600)

    def test_ollama_native_endpoint_is_accepted_directly(self):
        translator = NativeOllamaTranslator("http://server:11434/api/chat")

        self.assertEqual(
            translator._ollama_chat_endpoint(),
            "http://server:11434/api/chat",
        )

    def test_ollama_default_endpoint_does_not_override_other_providers(self):
        translator = NativeOllamaTranslator(OLLAMA_DEFAULT_ENDPOINT)
        translator._params['provider'] = 'OpenAI'

        self.assertIsNone(translator.endpoint)

    def test_vision_model_unload_setting_controls_pipeline_hook(self):
        translator = NativeOllamaTranslator()
        translator._params["unload vision models before llm"] = True
        self.assertTrue(translator.should_unload_before_llm_refinement())

        translator._params["unload vision models before llm"] = False
        self.assertFalse(translator.should_unload_before_llm_refinement())

    def test_num_ctx_setting_is_forwarded_to_native_ollama_options(self):
        translator = NativeOllamaTranslator()
        translator._params["num ctx"] = 32768

        translator._create_completion(
            {
                "model": "translategemma:12b",
                "messages": [{"role": "user", "content": "Translate."}],
                "extra_body": translator._build_reasoning_extra_body(),
            }
        )

        _, payload, _ = translator.client.requests[0]
        self.assertEqual(payload["options"]["num_ctx"], 32768)

    def test_two_step_defaults_to_native_ollama_base_url_and_context_setting(self):
        self.assertEqual(
            TwoStepTranslator.params["endpoint"]["value"],
            OLLAMA_DEFAULT_ENDPOINT,
        )
        self.assertIn("num ctx", TwoStepTranslator.params)
        self.assertIn(
            "Google Translate or DeepL",
            TwoStepTranslator.params["system_prompt"]["value"],
        )
        self.assertIn(
            "natural to a native reader",
            TwoStepTranslator.params["reflection prompt"]["value"],
        )

    def test_default_endpoint_and_model_preferences_are_available(self):
        self.assertEqual(
            LLM_API_Translator.params["endpoint"]["value"],
            OLLAMA_DEFAULT_ENDPOINT,
        )
        self.assertEqual(
            LLM_API_Translator.params["ollama model preferences"]["value"],
            {},
        )
        self.assertTrue(
            LLM_API_Translator.params["unload vision models before llm"]["value"]
        )
        self.assertTrue(
            LLM_API_Translator_2.params["unload vision models before llm"]["value"]
        )
        self.assertTrue(
            TwoStepTranslator.params["unload vision models before llm"]["value"]
        )

    def test_ollama_endpoint_helpers_normalize_openai_and_native_urls(self):
        self.assertEqual(
            ollama_chat_endpoint("http://127.0.0.1:11434/v1"),
            "http://127.0.0.1:11434/api/chat",
        )
        self.assertEqual(
            ollama_tags_endpoint("http://127.0.0.1:11434/api/chat"),
            "http://127.0.0.1:11434/api/tags",
        )

    def test_llm_two_step_source_supports_auto_but_target_does_not(self):
        translator = LLM_API_Translator("Auto", "English")

        self.assertIn("Auto", translator.supported_src_list)
        self.assertNotIn("Auto", translator.supported_tgt_list)


if __name__ == "__main__":
    unittest.main()
