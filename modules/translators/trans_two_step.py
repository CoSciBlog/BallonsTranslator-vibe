import json
import threading
import time
from copy import deepcopy
from json import JSONDecodeError
from typing import Any, Dict, List, Optional, Tuple

import requests
from pydantic import ValidationError

from .base import register_translator
from .trans_google import GoogleTranslateProviderPython, ProviderError
from .trans_llm_api import LLM_API_Translator, TranslationResponse


DEEPL_FREE_API_URL = "https://api-free.deepl.com/v2/translate"
DEEPL_API_URL = "https://api.deepl.com/v2/translate"


@register_translator("Two-Step Translator")
class TwoStepTranslator(LLM_API_Translator):
    concate_text = False
    cht_require_convert = True

    params: Dict = {
        "first step translator": {
            "type": "selector",
            "options": ["google", "DeepL Free", "DeepL"],
            "value": "google",
            "description": "Machine translator used for the first draft before LLM refinement.",
        },
        "deepl api key": {
            "value": "",
            "description": "DeepL or DeepL Free API key used when the first step translator is DeepL.",
        },
        "fallback to first step": {
            "type": "checkbox",
            "value": True,
            "description": "Use first-step draft translations if LLM refinement and strict retry fail.",
        },
        "first step delay": {
            "value": 0.5,
            "description": "Seconds to wait after each Google/DeepL first-step request. Increase this to reduce request bursts and lower the risk of temporary provider blocking; set to 0 for maximum speed.",
        },
        "parallel first step during pipeline": {
            "type": "checkbox",
            "value": False,
            "description": "During full RUN, start Google/DeepL draft translation in the background as soon as OCR finishes for a page. This can reduce total wall-clock time by overlapping network translation with later image work, but it increases concurrent API activity and does not make the final LLM refinement itself faster.",
        },
        "unload vision models before llm": {
            "type": "checkbox",
            "value": True,
            "description": "When parallel first-step translation is enabled, unload text detection, OCR, and inpainting models before final Ollama/LLM refinement. This frees RAM/VRAM for local LLMs and can prevent slowdowns or OOM on memory-limited GPUs, but unloading/reloading adds overhead.",
        },
        "max refinement items per request": {
            "value": 8,
            "description": "Maximum text blocks sent to each Two-Step LLM refinement request. Larger chunks reduce request count and can be faster, but bigger prompts may slow local models and increase JSON failure risk; smaller chunks are steadier but make more requests.",
        },
        **deepcopy(LLM_API_Translator.params),
    }
    params["provider"]["value"] = "Ollama"
    params["model"]["value"] = "OLLAMA: qwen3"
    params["endpoint"]["value"] = "http://localhost:11434/v1"
    params["system_prompt"][
        "value"
    ] = (
        "You are a translation editor. Improve draft machine translations by "
        "checking meaning, terminology, names, honorifics, pronouns, gendered "
        "address, speaker/addressee roles, tone, fluency, punctuation, and line "
        "count. Do not invent gender or relationships when the source is "
        "ambiguous. Return only valid JSON in this exact shape: "
        "{\"translations\":[{\"id\":1,\"translation\":\"...\"}]}. "
        "Do not include explanations."
    )

    def _setup_translator(self):
        super()._setup_translator()
        self.google_translator = GoogleTranslateProviderPython()
        self._draft_cache: Dict[Tuple[str, str, str, Tuple[str, ...]], List[str]] = {}
        self._draft_cache_lock = threading.RLock()
        self.last_refinement_used_draft_fallback = False
        self._last_draft_fallback_ids: List[int] = []

    @property
    def first_step_translator(self) -> str:
        return self.get_param_value("first step translator")

    @property
    def deepl_api_key(self) -> str:
        return self.get_param_value("deepl api key")

    @property
    def fallback_to_first_step(self) -> bool:
        return bool(self.get_param_value("fallback to first step"))

    @property
    def max_refinement_items_per_request(self) -> int:
        try:
            return max(1, int(float(self.get_param_value("max refinement items per request"))))
        except Exception:
            return 8

    @property
    def first_step_delay(self) -> float:
        try:
            return max(float(self.get_param_value("first step delay")), 0.0)
        except Exception:
            return 0.0

    @property
    def parallel_first_step_during_pipeline(self) -> bool:
        return bool(self.get_param_value("parallel first step during pipeline"))

    @property
    def unload_vision_models_before_llm(self) -> bool:
        return bool(self.get_param_value("unload vision models before llm"))

    def pipeline_pretranslation_enabled(self) -> bool:
        return self.parallel_first_step_during_pipeline

    def should_unload_before_llm_refinement(self) -> bool:
        return self.unload_vision_models_before_llm

    def _draft_cache_key(self, src_list: List[str]) -> Tuple[str, str, str, Tuple[str, ...]]:
        return (
            self.lang_source,
            self.lang_target,
            self.first_step_translator,
            tuple(src_list),
        )

    def _google_lang_map(self) -> Dict[str, str]:
        return {
            "Auto": "auto",
            "\u7b80\u4f53\u4e2d\u6587": "zh-CN",
            "\u7e41\u9ad4\u4e2d\u6587": "zh-TW",
            "\u65e5\u672c\u8a9e": "ja",
            "English": "en",
            "\ud55c\uad6d\uc5b4": "ko",
            "Ti\u1ebfng Vi\u1ec7t": "vi",
            "\u010de\u0161tina": "cs",
            "Nederlands": "nl",
            "Fran\u00e7ais": "fr",
            "Deutsch": "de",
            "magyar nyelv": "hu",
            "Italiano": "it",
            "Polski": "pl",
            "Portugu\u00eas": "pt",
            "limba rom\u00e2n\u0103": "ro",
            "\u0440\u0443\u0441\u0441\u043a\u0438\u0439 \u044f\u0437\u044b\u043a": "ru",
            "Espa\u00f1ol": "es",
            "T\u00fcrk dili": "tr",
            "\u0443\u043a\u0440\u0430\u0457\u0301\u043d\u0441\u044c\u043a\u0430 \u043c\u043e\u0301\u0432\u0430": "uk",
            "Thai": "th",
            "Arabic": "ar",
            "Hindi": "hi",
            "Malayalam": "ml",
            "Tamil": "ta",
        }

    def _deepl_lang_map(self) -> Dict[str, str]:
        return {
            "Auto": "",
            "\u7b80\u4f53\u4e2d\u6587": "ZH",
            "\u65e5\u672c\u8a9e": "JA",
            "English": "EN-US",
            "Fran\u00e7ais": "FR",
            "Deutsch": "DE",
            "Italiano": "IT",
            "Portugu\u00eas": "PT-PT",
            "Brazilian Portuguese": "PT-BR",
            "\u0440\u0443\u0441\u0441\u043a\u0438\u0439 \u044f\u0437\u044b\u043a": "RU",
            "Espa\u00f1ol": "ES",
            "Nederlands": "NL",
            "Polski": "PL",
            "\u010de\u0161tina": "CS",
            "\ud55c\uad6d\uc5b4": "KO",
            "Arabic": "AR",
        }

    def _translate_with_google(self, src_list: List[str]) -> List[str]:
        lang_map = self._google_lang_map()
        response = self.google_translator.translate(
            src_list,
            source_language=lang_map.get(self.lang_source, "auto"),
            target_language=lang_map.get(self.lang_target, "en"),
        )
        translations = response.get("translations", []) if response else []
        if len(translations) == len(src_list):
            return translations
        return [""] * len(src_list)

    def _translate_with_deepl(self, src_list: List[str], free: bool) -> List[str]:
        if not self.deepl_api_key:
            self.logger.error("DeepL first-step translation requires a DeepL API key.")
            return [""] * len(src_list)

        lang_map = self._deepl_lang_map()
        target_lang = lang_map.get(self.lang_target, "EN-US")
        source_lang = lang_map.get(self.lang_source, "")
        data = [("auth_key", self.deepl_api_key), ("target_lang", target_lang)]
        if source_lang:
            data.append(("source_lang", source_lang))
        for text in src_list:
            data.append(("text", text))

        url = DEEPL_FREE_API_URL if free else DEEPL_API_URL
        try:
            response = requests.post(url, data=data, timeout=30)
            response.raise_for_status()
            payload = response.json()
            translations = [
                item.get("text", "") for item in payload.get("translations", [])
            ]
            if len(translations) == len(src_list):
                return translations
        except Exception as e:
            self.logger.error(f"DeepL first-step translation failed: {e}")
        return [""] * len(src_list)

    def _first_step_translate(self, src_list: List[str]) -> List[str]:
        cache_key = self._draft_cache_key(src_list)
        with self._draft_cache_lock:
            cached = self._draft_cache.get(cache_key)
            if cached is not None:
                return list(cached)

        provider = self.first_step_translator
        draft_list = None
        try:
            if provider == "google":
                draft_list = self._translate_with_google(src_list)
            elif provider == "DeepL Free":
                draft_list = self._translate_with_deepl(src_list, free=True)
            elif provider == "DeepL":
                draft_list = self._translate_with_deepl(src_list, free=False)
            if draft_list is not None:
                with self._draft_cache_lock:
                    self._draft_cache[cache_key] = list(draft_list)
                delay = self.first_step_delay
                if delay > 0:
                    time.sleep(delay)
                return draft_list
        except ProviderError as e:
            self.logger.error(f"First-step translator provider error: {e}")
        except Exception as e:
            self.logger.error(f"First-step translation failed: {e}")
        return [""] * len(src_list)

    def _first_step_provider_label(self) -> str:
        provider = self.first_step_translator
        if provider == "google":
            return "Google"
        return provider

    def _store_first_step_results(self, textblk_lst, non_empty_ids: List[int], draft_list: List[str]) -> None:
        label = self._first_step_provider_label()
        self._store_provider_results(textblk_lst, non_empty_ids, draft_list, label=label)
        for ii, idx in enumerate(non_empty_ids):
            if ii >= len(draft_list):
                break
            textblk_lst[idx].translation_draft = draft_list[ii] or ''

    def _collect_translation_inputs(self, textblk_lst) -> Tuple[List[int], List[str], List[str]]:
        non_empty_ids = []
        text_list = []
        translations = []
        for ii, blk in enumerate(textblk_lst):
            text = blk.get_text()
            if text.strip() != "":
                non_empty_ids.append(ii)
                text_list.append(text)
            translations.append(text)

        for callback in self._preprocess_hooks.values():
            callback(
                translations=translations,
                textblocks=textblk_lst,
                translator=self,
                source_text=text_list,
            )
        return non_empty_ids, text_list, translations

    def pretranslate_textblk_lst(self, textblk_lst) -> None:
        non_empty_ids, src_list, _ = self._collect_translation_inputs(textblk_lst)
        if not src_list:
            return
        draft_list = self._first_step_translate(src_list)
        self._store_first_step_results(textblk_lst, non_empty_ids, draft_list)
        for ii, idx in enumerate(non_empty_ids):
            textblk_lst[idx].translation_draft = draft_list[ii]
        self.logger.info(
            f"Prepared first-step {self.first_step_translator} draft for {len(src_list)} text blocks."
        )

    def translate_textblk_lst(self, textblk_lst: List) -> None:
        non_empty_ids, text_list, translations = self._collect_translation_inputs(textblk_lst)
        if text_list:
            draft_list = self._first_step_translate(text_list)
            self._store_first_step_results(textblk_lst, non_empty_ids, draft_list)
            for ii, idx in enumerate(non_empty_ids):
                textblk_lst[idx].translation_draft = draft_list[ii]

            refined = self._refine_draft_translations(text_list, draft_list)
            for ii, idx in enumerate(non_empty_ids):
                translations[idx] = refined[ii]
                textblk_lst[idx].translation_draft_fallback = bool(
                    getattr(self, "last_refinement_used_draft_fallback", False)
                )

        for callback in self._postprocess_hooks.values():
            callback(
                translations=translations,
                textblocks=textblk_lst,
                translator=self,
            )

        for tr, blk in zip(translations, textblk_lst):
            blk.translation = tr

    def _expected_refinement_items(
        self, src_list: List[str], draft_list: List[str], start_id: int = 1
    ) -> List[Dict[str, Any]]:
        return [
            {"id": start_id + i, "source": source, "draft_translation": draft}
            for i, (source, draft) in enumerate(zip(src_list, draft_list))
        ]

    def _chunk_expected_items(self, expected_items: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        chunk_size = self.max_refinement_items_per_request
        return [
            expected_items[i : i + chunk_size]
            for i in range(0, len(expected_items), chunk_size)
        ]

    def _assemble_refinement_prompt_from_items(
        self, expected_items: List[Dict[str, Any]], to_lang: str
    ) -> str:
        from_lang = self.lang_map.get(self.lang_source, self.lang_source)
        expected_ids = [item["id"] for item in expected_items]
        return (
            f"Improve draft translations from {from_lang} to {to_lang}.\n"
            "Return valid JSON only. No markdown. No explanations. No comments. Never return {}.\n"
            'Use exactly this schema: { "translations": [ {"id": 1, "translation": "final improved translation"} ] }\n'
            f"Return the same number of items as the input: {len(expected_items)}.\n"
            f"Expected IDs: {expected_ids}.\n"
            "Return exactly one translation item for every input item.\n"
            "Preserve every id exactly. Do not add, remove, reorder, or merge items.\n"
            "If a draft is already good, return the draft unchanged.\n"
            "If unsure, return the draft unchanged.\n"
            "Keep the same target language.\n"
            "Verify pronouns, gendered wording, speaker/addressee roles, singular/plural first person, and formal/informal address against the source, draft, project context, and glossary.\n"
            "Do not turn a male character into a feminine pronoun/address, a female or girl character into a masculine pronoun/address, or I/me into we/us unless the source/context clearly requires it.\n"
            "Do not include source, draft_translation, category labels, glossary metadata, notes, or comments in the final output.\n"
            "The number of returned translations must equal the number of input items.\n\n"
            f"{self._review_quality_rules(len(expected_items), expected_ids)}"
            f"{self._translation_context_prompt_section()}"
            f"{self._review_glossary_prompt_section()}"
            f"INPUT:\n{json.dumps(expected_items, ensure_ascii=False, indent=2)}"
        )

    def _assemble_refinement_prompt(
        self, src_list: List[str], draft_list: List[str], to_lang: str
    ) -> str:
        return self._assemble_refinement_prompt_from_items(
            self._expected_refinement_items(src_list, draft_list),
            to_lang,
        )

    def _assemble_strict_refinement_retry_prompt(
        self, expected_items: List[Dict[str, Any]], to_lang: str
    ) -> str:
        expected_ids = [item["id"] for item in expected_items]
        return (
            f"Fix the previous LLM refinement response for {to_lang}.\n"
            "JSON only. Never return {}.\n"
            'Schema: {"translations":[{"id":1,"translation":"final improved translation"}]}\n'
            f"Required IDs: {expected_ids}.\n"
            "Return exactly these IDs. Do not omit IDs. Do not add IDs.\n"
            "Do not reorder, merge, or include source/draft_translation/metadata.\n"
            "If the draft is acceptable, copy it unchanged.\n"
            "If unsure, copy the draft unchanged.\n\n"
            f"INPUT:\n{json.dumps(expected_items, ensure_ascii=False, indent=2)}"
        )

    def _translation_items_by_id(
        self, response: Optional[TranslationResponse], label: str
    ) -> Dict[int, str]:
        items_by_id: Dict[int, str] = {}
        if not response:
            return items_by_id
        response = self._clean_translation_response(response)
        for item in response.translations:
            if not item.translation:
                continue
            if item.id in items_by_id:
                self.logger.warning(f"{label} duplicate id ignored: {item.id}")
                continue
            items_by_id[item.id] = item.translation
        return items_by_id

    def _log_refinement_shape(
        self, expected_ids: List[int], actual_ids: List[int], label: str
    ) -> Tuple[List[int], List[int]]:
        expected_set = set(expected_ids)
        actual_set = set(actual_ids)
        missing_ids = [item_id for item_id in expected_ids if item_id not in actual_set]
        extra_ids = [item_id for item_id in actual_ids if item_id not in expected_set]
        log_message = (
            f"{label} expected_count={len(expected_ids)} actual_count={len(actual_ids)} "
            f"missing_ids={missing_ids} extra_ids={extra_ids}"
        )
        if missing_ids or extra_ids or len(actual_ids) != len(expected_ids):
            self.logger.warning(log_message)
        else:
            self.logger.info(log_message)
        return missing_ids, extra_ids

    def merge_refinement_with_drafts(
        self,
        expected_items: List[Dict[str, Any]],
        normal_response: Optional[TranslationResponse],
        retry_response: Optional[TranslationResponse],
        fallback_to_first_step: bool = True,
    ) -> List[str]:
        expected_ids = [int(item["id"]) for item in expected_items]
        normal_by_id = self._translation_items_by_id(normal_response, "normal_refinement")
        retry_by_id = self._translation_items_by_id(retry_response, "strict_refinement_retry")
        available_ids = set(normal_by_id) | set(retry_by_id)
        missing_ids = [item_id for item_id in expected_ids if item_id not in available_ids]
        extra_ids = sorted((set(normal_by_id) | set(retry_by_id)) - set(expected_ids))
        if missing_ids:
            self.logger.warning(f"Missing refinement ids: {missing_ids}")
        if extra_ids:
            self.logger.warning(f"Extra refinement ids ignored: {extra_ids}")

        merged = []
        for item in expected_items:
            item_id = int(item["id"])
            if item_id in retry_by_id:
                merged.append(retry_by_id[item_id])
            elif item_id in normal_by_id:
                merged.append(normal_by_id[item_id])
            elif fallback_to_first_step:
                if not hasattr(self, "_last_draft_fallback_ids"):
                    self._last_draft_fallback_ids = []
                self._last_draft_fallback_ids.append(item_id)
                merged.append(item.get("draft_translation") or item.get("source") or "")
        return merged

    def _response_covers_expected_ids(
        self, response: Optional[TranslationResponse], expected_ids: List[int], label: str
    ) -> bool:
        actual_ids = list(self._translation_items_by_id(response, label).keys())
        missing_ids, extra_ids = self._log_refinement_shape(expected_ids, actual_ids, label)
        return not missing_ids and not extra_ids and len(actual_ids) == len(expected_ids)

    def _request_refinement_chunk(
        self, expected_items: List[Dict[str, Any]], to_lang: str
    ) -> Tuple[Optional[TranslationResponse], Optional[TranslationResponse]]:
        expected_ids = [int(item["id"]) for item in expected_items]
        normal_response = None
        retry_response = None

        try:
            normal_prompt = self._assemble_refinement_prompt_from_items(expected_items, to_lang)
            normal_response = self._request_translation(
                normal_prompt,
                is_reflection=True,
                purpose="normal_refinement",
                expected_count=len(expected_items),
                expected_ids=expected_ids,
                max_tokens_override=min(max(self.max_tokens, 2048), 8192),
            )
            if self._response_covers_expected_ids(normal_response, expected_ids, "normal_llm_refinement"):
                return normal_response, None
            normal_ids = set(
                self._translation_items_by_id(normal_response, "normal_llm_refinement").keys()
            )
            if normal_ids & set(expected_ids):
                self.logger.warning(
                    "LLM refinement returned partial response; using ID-matched refined translations and drafts for missing IDs."
                )
            self.logger.warning("normal_llm_refinement failed")
        except Exception as e:
            self.logger.warning("normal_llm_refinement failed")
            self.logger.debug(f"normal_llm_refinement details: {type(e).__name__}: {e}")

        try:
            self.logger.info("strict_refinement_retry retry started")
            retry_prompt = self._assemble_strict_refinement_retry_prompt(expected_items, to_lang)
            retry_response = self._request_translation(
                retry_prompt,
                is_reflection=True,
                purpose="strict_refinement_retry",
                expected_count=len(expected_items),
                expected_ids=expected_ids,
                max_tokens_override=min(max(self.max_tokens, 2048), 4096),
            )
            if self._response_covers_expected_ids(retry_response, expected_ids, "strict_refinement_retry"):
                self.logger.info("strict_refinement_retry retry succeeded")
            else:
                self.logger.warning("strict_refinement_retry retry failed")
        except Exception as e:
            self.logger.warning("strict_refinement_retry retry failed")
            self.logger.debug(f"strict_refinement_retry details: {type(e).__name__}: {e}")

        return normal_response, retry_response

    def _translate(self, src_list: List[str]) -> List[str]:
        if not src_list:
            return []

        draft_list = self._first_step_translate(src_list)
        return self._refine_draft_translations(src_list, draft_list)

    def _refine_draft_translations(self, src_list: List[str], draft_list: List[str]) -> List[str]:
        to_lang = self.lang_map.get(self.lang_target, self.lang_target)
        glossary_drafts = [
            draft or source for source, draft in zip(src_list, draft_list)
        ]
        self._update_glossary_from_batch(src_list, glossary_drafts, to_lang)
        expected_items = self._expected_refinement_items(src_list, draft_list)
        self.last_refinement_used_draft_fallback = False
        self._last_draft_fallback_ids = []
        translations: List[str] = []

        for chunk in self._chunk_expected_items(expected_items):
            normal_response, retry_response = self._request_refinement_chunk(chunk, to_lang)
            chunk_translations = self.merge_refinement_with_drafts(
                chunk,
                normal_response,
                retry_response,
                fallback_to_first_step=self.fallback_to_first_step,
            )
            if len(chunk_translations) < len(chunk):
                self.logger.warning(
                    "LLM refinement and strict retry failed and first-step draft fallback is disabled."
                )
                chunk_translations.extend([""] * (len(chunk) - len(chunk_translations)))
            translations.extend(chunk_translations)

        if self.fallback_to_first_step:
            used_draft = bool(self._last_draft_fallback_ids)
            self.last_refinement_used_draft_fallback = used_draft
            if used_draft:
                self.logger.warning(
                    f"draft fallback used for ids={self._last_draft_fallback_ids}"
                )
            if used_draft and not any(draft_list):
                self.logger.warning(
                    "LLM refinement failed and no first-step draft translations were available."
                )

        return self._refine_translations_with_glossary(
            src_list, translations, to_lang
        )

    def review_translations(self, src_list: List[str], draft_list: List[str]) -> List[str]:
        return self._refine_draft_translations(src_list, draft_list)
