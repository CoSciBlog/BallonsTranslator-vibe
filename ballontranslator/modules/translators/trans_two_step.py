"""Machine-translation draft followed by an Ollama refinement pass."""

import json
from dataclasses import replace
from typing import Dict, List, Optional, Union

import requests

from ballontranslator.modules.exceptions import LLMRequestStopped
from ballontranslator.utils.llm_profiles import (
    LLMProfile,
    ollama_native_chat_url,
)

from .base import register_translator
from .trans_google import GoogleTranslateProviderPython, ProviderError
from .trans_llm import LLMTranslator


DEEPL_API_URL = "https://api.deepl.com/v2/translate"
DEEPL_FREE_API_URL = "https://api-free.deepl.com/v2/translate"

TWO_STEP_REFINEMENT_PROMPT = """You are the second step of a translation pipeline.
Each input item is JSON with `source` and `draft_translation`. Check the machine
translation against the source, then return a faithful, fluent final translation
in the requested target language. Preserve meaning, tone, names, honorifics,
formatting, and explicit content. Correct omissions and mistranslations. If the
draft is already accurate, keep it. Output only the final translation for each
item; never include the JSON fields, explanations, or notes.

Additional profile instructions:
"""


@register_translator("Two-Step (Google/DeepL + Ollama)")
class TwoStepTranslator(LLMTranslator):
    """Create Google/DeepL drafts and refine them with the selected Ollama profile.

    The second pass reuses the regular LLM translator's context, glossary,
    retry, and response handling.

    >>> TwoStepTranslator.__name__
    'TwoStepTranslator'
    """

    concate_text = False
    dependencies = ['openai>=2.8.1', 'httpx[socks,brotli]', 'tiktoken>=0.7.0']
    params: Dict = {
        "description": (
            "Translate with Google or DeepL first, then review and refine the "
            "draft with the selected local Ollama text profile."
        ),
        "first step translator": {
            "type": "selector",
            "options": ["Google", "DeepL Free", "DeepL Pro"],
            "value": "Google",
            "display_name": "First-Step Translator",
        },
        "deepl api key": {
            "value": "",
            "type": "secret",
            "display_name": "DeepL API Key",
        },
        "fallback to first step": {
            "value": True,
            "display_name": "Use Draft If Ollama Fails",
        },
        "first step delay": {
            "value": 0.0,
            "display_name": "First-Step Delay",
            "description": "Delay after machine translation in seconds.",
        },
        "google auto detect source": {
            "value": True,
            "display_name": "Google Auto-Detect Source Language",
        },
        "max requests per minute": {
            "value": 20,
            "display_name": "Max Requests Per Minute",
            "description": "Global request limit for Ollama refinement.",
        },
        "delay": {"value": 0.3, "display_name": "Ollama Request Delay"},
        "retry attempts": {"value": 5, "display_name": "Ollama Retry Attempts"},
        "retry timeout": {"value": 7.0, "display_name": "Ollama Retry Timeout"},
        "proxy": {"value": "", "display_name": "Proxy"},
    }

    def _setup_translator(self) -> None:
        super()._setup_translator()
        # Keep language metadata literal so the lazy registry can populate the
        # selector without importing the LLM implementation.
        self.lang_map.update({
            'Auto': 'the automatically detected source language',
            '简体中文': 'Simplified Chinese',
            '繁體中文': 'Traditional Chinese',
            '日本語': 'Japanese',
            'English': 'English',
            '한국어': 'Korean',
            'Tiếng Việt': 'Vietnamese',
            'čeština': 'Czech',
            'Français': 'French',
            'Deutsch': 'German',
            'magyar nyelv': 'Hungarian',
            'Italiano': 'Italian',
            'Polski': 'Polish',
            'Português': 'Portuguese',
            'limba română': 'Romanian',
            'русский язык': 'Russian',
            'Español': 'Spanish',
            'Türk dili': 'Turkish',
            'украї́нська мо́ва': 'Ukrainian',
            'Thai': 'Thai',
            'Arabic': 'Arabic',
            'Malayalam': 'Malayalam',
            'Tamil': 'Tamil',
            'Hindi': 'Hindi',
        })
        self._google = GoogleTranslateProviderPython()

    @property
    def profile(self) -> LLMProfile:
        profile = super().profile
        if not ollama_native_chat_url(profile):
            raise RuntimeError(
                "Two-step translation requires a local Ollama LLM profile "
                "(for example http://127.0.0.1:11434/v1)."
            )
        return replace(
            profile,
            prompt=TWO_STEP_REFINEMENT_PROMPT + str(profile.prompt or ""),
        )

    @property
    def first_step_translator(self) -> str:
        return str(self.get_param_value("first step translator"))

    @property
    def fallback_to_first_step(self) -> bool:
        return bool(self.get_param_value("fallback to first step"))

    def translation_run_description(self) -> str:
        return (
            f"Two-step translation: first_step={self.first_step_translator!r}, "
            + super().translation_run_description()
        )

    @staticmethod
    def _google_language(language: str, default: str) -> str:
        codes = {
            "简体中文": "zh-CN", "繁體中文": "zh-TW", "日本語": "ja",
            "English": "en", "한국어": "ko", "Tiếng Việt": "vi",
            "čeština": "cs", "Nederlands": "nl", "Français": "fr",
            "Deutsch": "de", "magyar nyelv": "hu", "Italiano": "it",
            "Polski": "pl", "Português": "pt", "limba română": "ro",
            "русский язык": "ru", "Español": "es", "Türk dili": "tr",
            "украї́нська мо́ва": "uk", "Thai": "th", "Arabic": "ar",
            "Hindi": "hi", "Malayalam": "ml", "Tamil": "ta",
        }
        return codes.get(language, default)

    def _translate_google(self, source: List[str]) -> List[str]:
        auto_detect = bool(self.get_param_value("google auto detect source"))
        response = self._google.translate(
            source,
            target_language=self._google_language(self.lang_target, "en"),
            source_language=(
                "auto"
                if auto_detect or self.lang_source == "Auto"
                else self._google_language(self.lang_source, "auto")
            ),
        )
        translations = response.get("translations", []) if response else []
        if len(translations) != len(source):
            raise ProviderError("Google returned an unexpected translation count.")
        return [str(text or "") for text in translations]

    @staticmethod
    def _deepl_language(language: str, *, target: bool) -> str:
        codes = {
            "Auto": "", "简体中文": "ZH", "繁體中文": "ZH-HANT" if target else "ZH",
            "日本語": "JA", "English": "EN-US" if target else "EN",
            "한국어": "KO", "Français": "FR", "Deutsch": "DE",
            "Italiano": "IT", "Nederlands": "NL", "Polski": "PL",
            "Português": "PT-PT" if target else "PT", "русский язык": "RU",
            "Español": "ES", "Türk dili": "TR", "украї́нська мо́ва": "UK",
        }
        return codes.get(language, "")

    def _translate_deepl(self, source: List[str], *, free: bool) -> List[str]:
        api_key = str(self.get_param_value("deepl api key") or "").strip()
        if not api_key:
            raise RuntimeError("DeepL first-step translation requires an API key.")
        target_language = self._deepl_language(self.lang_target, target=True)
        if not target_language:
            raise RuntimeError(f"DeepL does not support target language: {self.lang_target}")
        data = [("auth_key", api_key), ("target_lang", target_language)]
        source_language = self._deepl_language(self.lang_source, target=False)
        if source_language:
            data.append(("source_lang", source_language))
        data.extend(("text", text) for text in source)
        response = requests.post(
            DEEPL_FREE_API_URL if free else DEEPL_API_URL,
            data=data,
            timeout=30,
        )
        response.raise_for_status()
        translations = [
            str(item.get("text", ""))
            for item in response.json().get("translations", [])
        ]
        if len(translations) != len(source):
            raise RuntimeError("DeepL returned an unexpected translation count.")
        return translations

    def _first_step(self, source: List[str]) -> List[str]:
        provider = self.first_step_translator
        if provider == "Google":
            drafts = self._translate_google(source)
        elif provider == "DeepL Free":
            drafts = self._translate_deepl(source, free=True)
        elif provider == "DeepL Pro":
            drafts = self._translate_deepl(source, free=False)
        else:
            raise RuntimeError(f"Unknown first-step translator: {provider}")
        wait_seconds = max(0.0, float(self.get_param_value("first step delay")))
        if wait_seconds:
            self._wait(wait_seconds)
        return drafts

    @staticmethod
    def _review_input(source: str, draft: str) -> str:
        return json.dumps(
            {"source": source, "draft_translation": draft},
            ensure_ascii=False,
        )

    def translate(
        self,
        text: Optional[Union[str, List[str]]],
        *,
        project=None,
        page_key: Optional[str] = None,
        commit_history_window: bool = False,
    ) -> Optional[Union[str, List[str]]]:
        if text is None or text == "" or text == []:
            return text
        # Reject a remote/non-Ollama profile before sending text to the first
        # provider; configuration errors must not look like a successful draft fallback.
        _ = self.profile
        is_list = isinstance(text, list)
        source = list(text) if is_list else [str(text)]
        drafts = self._first_step(source)
        review_input = [
            self._review_input(original, draft)
            for original, draft in zip(source, drafts)
        ]
        try:
            refined = super().translate(
                review_input,
                project=project,
                page_key=page_key,
                commit_history_window=commit_history_window,
            )
        except LLMRequestStopped:
            raise
        except Exception as error:
            if not self.fallback_to_first_step:
                raise
            self.logger.warning(
                "Ollama refinement failed; keeping first-step translations "
                "(%s).",
                type(error).__name__,
            )
            refined = drafts
        result = list(refined) if isinstance(refined, list) else [str(refined or "")]
        if self.fallback_to_first_step:
            result = [final or draft for final, draft in zip(result, drafts)]
        return result if is_list else result[0]
