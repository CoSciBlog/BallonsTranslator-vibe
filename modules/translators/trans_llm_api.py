import re
import time
import json
import traceback
import unicodedata
from types import SimpleNamespace
from typing import Any, List, Dict, Optional, Set, Tuple, Type

import httpx
import openai
from pydantic import BaseModel, Field, ValidationError

from .base import BaseTranslator, register_translator


class InvalidNumTranslations(Exception):
    """Exception raised when the number of translations does not match the number of sources."""

    pass


class TranslationElement(BaseModel):
    id: int = Field(..., description="The original numeric ID of the text snippet.")
    translation: str = Field(
        ..., description="The translated text corresponding to the id."
    )


class TranslationResponse(BaseModel):
    translations: List[TranslationElement] = Field(
        ..., description="A list of all translated elements."
    )


class GlossaryEntry(BaseModel):
    source: str = Field(..., description="Source glossary item allowed by the enabled category filters.")
    target: str = Field(..., description="Preferred translated form.")
    category: str = Field(
        default="term",
        description="Enabled category key such as character, place, organization, title, term, honorific, or catchphrase.",
    )
    aliases: List[str] = Field(default_factory=list, description="Alternative spellings or romanizations.")
    note: str = Field(default="", description="Short optional usage note.")
    confidence: float = Field(default=0.0, description="Optional model confidence from 0.0 to 1.0.")


class GlossaryResponse(BaseModel):
    entries: List[GlossaryEntry] = Field(
        default_factory=list,
        description="Reusable glossary entries extracted from translated text.",
    )


AUTO_GLOSSARY_CATEGORY_CONFIG = {
    "character": {
        "param": "auto glossary names",
        "label": "character/person names and nicknames",
        "aliases": {"character", "person", "name", "names", "nickname", "nicknames"},
    },
    "place": {
        "param": "auto glossary places",
        "label": "place/location names",
        "aliases": {"place", "places", "location", "locations"},
    },
    "organization": {
        "param": "auto glossary organizations",
        "label": "organization/group names",
        "aliases": {"organization", "organisation", "group", "clan", "school", "sect"},
    },
    "title": {
        "param": "auto glossary titles",
        "label": "titles and honorific titles",
        "aliases": {"title", "titles"},
    },
    "term": {
        "param": "auto glossary terms",
        "label": "domain terms and named items",
        "aliases": {"term", "terms", "domain term", "special term", "named item", "item"},
    },
    "honorific": {
        "param": "auto glossary honorifics",
        "label": "honorifics and forms of address",
        "aliases": {"honorific", "honorifics", "address", "form of address"},
    },
    "catchphrase": {
        "param": "auto glossary catchphrases",
        "label": "catchphrases and fixed phrases",
        "aliases": {"catchphrase", "catchphrases", "phrase", "phrases", "fixed phrase"},
    },
}

REVIEW_GLOSSARY_CATEGORIES = ("character", "honorific", "title", "place", "organization")
GLOSSARY_JA_HONORIFICS = ("ちゃん", "くん", "さん", "先輩", "先生", "様")
GLOSSARY_REACTION_TARGETS = {
    "ah",
    "ahh",
    "aha",
    "huh",
    "hmph",
    "tsk",
    "ugh",
    "hehe",
    "sorry",
    "wait",
    "yes",
    "no",
    "oh",
    "ooh",
    "ow",
    "ouch",
    "eek",
    "kya",
    "um",
    "uh",
    "hmm",
}
GLOSSARY_INTERJECTION_STEMS = {
    "",
    "あ",
    "あん",
    "きゃ",
    "きゃあ",
    "ふ",
    "ち",
    "ん",
    "はぁ",
    "はあ",
    "ひ",
    "く",
    "う",
    "へへ",
    "おほ",
    "いや",
    "ええ",
    "な",
}
GLOSSARY_DIALOGUE_SOURCE_PATTERNS = (
    "待って",
    "ごめん",
    "すみません",
    "止めて",
    "払え",
    "もういい",
    "いいや",
    "じゃない",
    "ではない",
    "ください",
    "オメー",
    "おまえ",
    "これも",
    "タクシー",
)
GLOSSARY_TITLE_SOURCE_MARKERS = (
    "先生",
    "先輩",
    "様",
    "殿",
    "社長",
    "部長",
    "課長",
    "係長",
    "店長",
    "監督",
    "隊長",
    "博士",
    "教授",
    "王",
    "女王",
    "姫",
    "皇帝",
    "章",
    "巻",
    "話",
    "編",
)
GLOSSARY_TITLE_TARGET_MARKERS = (
    "mr",
    "mrs",
    "ms",
    "miss",
    "dr",
    "professor",
    "teacher",
    "senpai",
    "sensei",
    "lord",
    "lady",
    "king",
    "queen",
    "captain",
    "chief",
    "president",
    "director",
    "manager",
    "chapter",
    "episode",
    "volume",
    "rank",
    "title",
)


def canonicalize_glossary_category(category: str) -> str:
    raw_category = (category or "").strip().lower()
    raw_category = raw_category.strip("[](){}")
    raw_category = re.sub(r"\s+", " ", raw_category)
    raw_category = raw_category.removesuffix(" name")
    for canonical, config in AUTO_GLOSSARY_CATEGORY_CONFIG.items():
        if raw_category in config["aliases"]:
            return canonical
    return raw_category or "term"


def _category_param_description(label: str) -> str:
    return f"Allow automatic glossary extraction for {label}. Disable it to keep auto glossary entries narrower."


@register_translator("LLM_API_Translator")
class LLM_API_Translator(BaseTranslator):
    concate_text = False
    cht_require_convert = True
    params: Dict = {
        "provider": {
            "type": "selector",
            "options": ["OpenAI", "Google", "Grok", "OpenRouter", "LLM Studio", "Ollama"],
            "value": "OpenAI",
            "description": "Select the LLM provider. Translation speed depends on provider latency, queueing, rate limits, JSON support, and for local providers the CPU/GPU and model size.",
        },
        "apikey": {
            "value": "",
            "description": "Single API key to use if multiple keys are not provided. The key itself does not make translation faster, but provider quotas and rate limits can throttle request throughput.",
        },
        "multiple_keys": {
            "type": "editor",
            "value": "",
            "description": "API keys separated by semicolons (;). Requests rotate through these keys, which can improve throughput when a provider rate-limits each key separately.",
        },
        "model": {
            "type": "selector",
            "options": [
                "OAI: gpt-4o",
                "OAI: gpt-4.1",
                "OAI: gpt-4.1-mini",
                "OAI: o4-mini",
                "OAI: gpt-4-turbo",
                "OAI: gpt-3.5-turbo",
                "GGL: gemini-1.5-pro-latest",
                "GGL: gemini-2.5-flash",
                "GGL: gemini-2.5-flash-lite",
                "XAI: grok-4",
                "XAI: grok-3",
                "XAI: grok-3-mini",
                "OR: qwen/qwen3-235b-a22b",
                "OR: qwen/qwen3-32b",
                "OR: google/gemma-3-27b-it",
                "OR: (override model field)",
                "LLMS: (override model field)",
                "OLLAMA: qwen3",
                "OLLAMA: gemma3",
                "OLLAMA: (override model field)",
            ],
            "value": "OAI: gpt-4o",
            "description": "Select a model that supports structured JSON output, or use the override field for newer model IDs.",
        },
        "override model": {
            "value": "",
            "description": "Specify a custom model name to override the selected model.",
        },
        "endpoint": {
            "value": "",
            "description": "Base URL for the API. Leave empty for provider default. Ollama uses its native /api/chat endpoint; an existing URL ending in /v1 is accepted and normalized automatically.",
        },
        "system_prompt": {
            "type": "editor",
            "value": 'You are an expert manga/comic translator and editor. Translate accurately and naturally while preserving speaker intent, character relationships, names, honorifics, pronouns, number, gender, and formal/informal address from the source and available context. Do not invent gender, pronouns, relationships, or names when the source is ambiguous; keep ambiguity natural in the target language. You MUST provide the output strictly in the specified JSON format, without any additional explanations or markdown formatting. Return only valid JSON in this exact shape: {"translations":[{"id":1,"translation":"Translated text here."}]}. The JSON object must have a single key \'translations\', which is a list of objects, each with an \'id\' (integer) and a \'translation\' (string).\n\nExample Output Schema:\n{"translations": [{"id": 1, "translation": "Translated text here."}]}',
            "description": "System message to instruct the LLM on its role and required output format. Available placeholders: {source_language} / {input_language} / {from_lang} for the source language, and {target_language} / {output_language} / {to_lang} for the target language. JSON braces that do not match these names are left unchanged.",
        },
        "invalid repeat count": {
            "value": 2,
            "description": "Number of retries if the count of translations mismatches the source count.",
        },
        "max requests per minute": {
            "value": 20,
            "description": "Maximum requests per minute for EACH API key.",
        },
        "delay": {
            "value": 0.3,
            "description": "Global delay in seconds between LLM requests. Higher values deliberately slow translation to avoid provider rate limits; lower values maximize throughput.",
        },
        "max tokens": {
            "value": 4096,
            "description": "Maximum tokens for the response. Very high values can slow down local models and make JSON output less stable.",
        },
        "reasoning": {
            "type": "checkbox",
            "value": False,
            "description": "Ask supported models to use reasoning controls. This can improve difficult edits, but usually increases latency and token work; disabling it is faster and often more stable for JSON translation.",
        },
        "reasoning level": {
            "type": "selector",
            "options": ["low", "medium", "high"],
            "value": "medium",
            "description": "Reasoning effort used when reasoning is enabled. Higher levels can spend more time and tokens per request; low is usually the fastest option.",
        },
        "json mode": {
            "type": "checkbox",
            "value": True,
            "description": "Request structured JSON output from OpenAI-compatible providers when supported. It can reduce parse retries and speed up failed batches, but unsupported or strict providers may add overhead or require fallback.",
        },
        "num ctx": {
            "value": 0,
            "description": "Ollama context window size passed as native options.num_ctx. 0 leaves the Ollama/server default unchanged. Larger contexts require more RAM/VRAM.",
        },
        "reflection": {
            "type": "checkbox",
            "value": False,
            "description": "Run an additional LLM review pass after translation. This adds another LLM request for each batch, so translation is slower and uses more tokens.",
        },
        "review speed mode": {
            "type": "selector",
            "options": [
                "Thorough (separate passes)",
                "Combined review (fast)",
                "Reflection only (fastest)",
                "No additional review",
            ],
            "value": "Thorough (separate passes)",
            "description": "Controls optional correction requests. Combined review checks active glossary guidance during the reflection request and skips the separate glossary-refinement request. Auto glossary extraction remains a separate request when enabled.",
        },
        "bubble text shortening": {
            "type": "selector",
            "options": [
                "Off",
                "Shorten extremely long translations",
                "Shorten long and extremely long translations",
            ],
            "value": "Off",
            "description": "Ask the LLM to compress long dialogue for comic speech bubbles while preserving meaning, tone, names, and important details. This guides rewriting; it never blindly truncates text.",
        },
        "long bubble character target": {
            "value": 90,
            "description": "Approximate character target for long translations when full shortening is enabled. Lower values produce tighter dialogue but increase the risk of losing nuance.",
        },
        "extreme bubble character target": {
            "value": 140,
            "description": "Approximate character target for extremely long translations. Lines beyond this target are condensed in either shortening mode when possible without changing meaning.",
        },
        "reflection prompt": {
            "type": "editor",
            "value": "Review the draft translation against the original source text. Check meaning, terminology, names, glossary terms, tone, fluency, punctuation, item count, pronouns, speaker/addressee references, gendered wording, singular/plural first person, and formal/informal address. Revise only where the translation can be improved. Return only the final improved JSON object in the required schema.",
            "description": "Instructions used for the optional reflection/revision API call. Available placeholders: {source_language} / {input_language} / {from_lang} for the source language, and {target_language} / {output_language} / {to_lang} for the target language. Reflection receives the original translation task and draft JSON automatically.",
        },
        "previous context pages": {
            "value": 0,
            "description": "Number of previous project pages included as source and existing translation context. More pages improve continuity but enlarge prompts, increasing latency, token use, and local model memory pressure.",
        },
        "include next context page": {
            "type": "checkbox",
            "value": False,
            "description": "Also include the next project page when text is available. This can improve names and references, but adds prompt text and can slow each LLM request.",
        },
        "document context pages": {
            "value": 0,
            "description": "Include up to this many pages from the project as document-level context for each LLM batch. Higher values can improve consistency but increase prompt size, cost, and response time.",
        },
        "context max characters": {
            "value": 6000,
            "description": "Maximum characters allowed for all LLM context sections combined before truncation. Raising this gives the model more context but usually slows requests; lowering it is faster for small context windows.",
        },
        "use glossary": {
            "type": "checkbox",
            "value": True,
            "description": "Include the current project's glossary.json entries in translation prompts. This improves term consistency, but larger glossaries increase prompt size, token use, and request latency.",
        },
        "auto build glossary": {
            "type": "checkbox",
            "value": True,
            "description": "After each LLM translation batch, ask the model to extract reusable glossary entries from the source/translation pairs. This improves later consistency but adds extra LLM calls and slows translation.",
        },
        "auto glossary names": {
            "type": "checkbox",
            "value": True,
            "description": _category_param_description("character/person names and nicknames"),
        },
        "auto glossary places": {
            "type": "checkbox",
            "value": True,
            "description": _category_param_description("place/location names"),
        },
        "auto glossary organizations": {
            "type": "checkbox",
            "value": False,
            "description": _category_param_description("organization/group names"),
        },
        "auto glossary titles": {
            "type": "checkbox",
            "value": False,
            "description": _category_param_description("titles"),
        },
        "auto glossary terms": {
            "type": "checkbox",
            "value": False,
            "description": _category_param_description("domain terms and named items"),
        },
        "auto glossary honorifics": {
            "type": "checkbox",
            "value": False,
            "description": _category_param_description("honorifics and forms of address"),
        },
        "auto glossary catchphrases": {
            "type": "checkbox",
            "value": False,
            "description": _category_param_description("catchphrases and fixed phrases"),
        },
        "glossary refinement pass": {
            "type": "checkbox",
            "value": True,
            "description": "Run a dedicated follow-up pass to apply the current glossary to translations. This adds extra LLM requests; Combined review skips it and checks the glossary in reflection instead.",
        },
        "glossary max entries": {
            "value": 200,
            "description": "Maximum number of entries kept in the current project's glossary.json. Higher values preserve more terms but increase prompt size, token cost, and latency when use glossary is enabled.",
        },
        "temperature": {
            "value": 0.1,
            "description": "Sampling temperature. Lower values are recommended for structured output.",
        },
        "top p": {
            "value": 1.0,
            "description": "Top P for sampling.",
        },
        "retry attempts": {
            "value": 3,
            "description": "Number of retry attempts on API connection or parsing failures.",
        },
        "retry timeout": {
            "value": 15,
            "description": "Timeout between retry attempts (seconds).",
        },
        "proxy": {
            "value": "",
            "description": "Proxy address (e.g., http(s)://user:password@host:port or socks4/5://user:password@host:port)",
        },
        "frequency penalty": {
            "value": 0.0,
            "description": "Frequency penalty (OpenAI).",
        },
        "presence penalty": {"value": 0.0, "description": "Presence penalty (OpenAI)."},
        "low vram mode": {
            'value': False,
            'description': 'Use this for local single-device runs that crash from VRAM exhaustion. It is a memory-safety option, not a speed boost; it prevents translation from running in parallel with the image pipeline and can increase total runtime.',
            'type': 'checkbox',
        }
    }

    def _setup_translator(self):
        self.lang_map = {
            "Auto": "Auto-detected source language",
            "简体中文": "Simplified Chinese",
            "繁體中文": "Traditional Chinese",
            "日本語": "Japanese",
            "English": "English",
            "한국어": "Korean",
            "Tiếng Việt": "Vietnamese",
            "čeština": "Czech",
            "Français": "French",
            "Deutsch": "German",
            "magyar nyelv": "Hungarian",
            "Italiano": "Italian",
            "Polski": "Polish",
            "Português": "Portuguese",
            "limba română": "Romanian",
            "русский язык": "Russian",
            "Español": "Spanish",
            "Türk dili": "Turkish",
            "украї́нська мо́ва": "Ukrainian",
            "Thai": "Thai",
            "Arabic": "Arabic",
            "Malayalam": "Malayalam",
            "Tamil": "Tamil",
            "Hindi": "Hindi",
        }
        self.token_count = 0
        self.token_count_last = 0
        self.current_key_index = 0
        self.last_request_time = 0
        self.request_count_minute = 0
        self.minute_start_time = time.time()
        self.key_usage = {}
        self.client = None
        self.project_glossary_text = ""
        self.project_glossary_prompt = ""
        self.project_glossary_reference_text = ""
        self.project_glossary_reference_prompt = ""
        self.project_glossary_loaded = False
        self.context_project = None
        self.context_page_key = ""

    @property
    def supported_tgt_list(self) -> List[str]:
        return [lang for lang in self.valid_lang_list if lang != "Auto"]

    def _initialize_client(self, api_key_to_use: str) -> bool:
        endpoint = self.endpoint
        provider = self.provider
        if not endpoint:
            if provider == "Google":
                endpoint = "https://generativelanguage.googleapis.com/v1beta/openai"
            elif provider == "OpenAI":
                endpoint = "https://api.openai.com/v1"
            elif provider == "OpenRouter":
                endpoint = "https://openrouter.ai/api/v1"
            elif provider == "Grok":
                endpoint = "https://api.x.ai/v1"
            elif provider == "Ollama":
                endpoint = "http://localhost:11434"

        proxy = self.proxy
        http_client = None
        if proxy:
            try:
                proxy_mounts = {
                    "http://": httpx.HTTPTransport(proxy=proxy),
                    "https://": httpx.HTTPTransport(proxy=proxy),
                }
                http_client = httpx.Client(mounts=proxy_mounts)
            except Exception as e:
                self.logger.error(
                    f"Failed to initialize proxy '{proxy}': {e}. Proceeding without proxy."
                )
                http_client = httpx.Client()
        else:
            http_client = httpx.Client()

        masked_key = (
            api_key_to_use[:4] + "..." + api_key_to_use[-4:]
            if len(api_key_to_use) > 8
            else api_key_to_use
        )
        self.logger.debug(
            f"Initializing client for {provider} with key {masked_key} at endpoint {endpoint}"
        )

        try:
            if provider == "Ollama":
                self.client = http_client
                return True
            self.client = openai.OpenAI(
                api_key=api_key_to_use, base_url=endpoint, http_client=http_client
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize OpenAI client: {e}")
            self.client = None
            return False

    # --- Property getters ---
    @property
    def provider(self) -> str:
        return self.get_param_value("provider")

    @property
    def apikey(self) -> str:
        return self.get_param_value("apikey")

    @property
    def multiple_keys_list(self) -> List[str]:
        keys_str = self.get_param_value("multiple_keys")
        if not isinstance(keys_str, str):
            return []
        return [
            key.strip()
            for key in keys_str.strip().replace("\n", ";").split(";")
            if key.strip()
        ]

    @property
    def model(self) -> str:
        return self.get_param_value("model")

    @property
    def override_model(self) -> Optional[str]:
        return self.get_param_value("override model") or None

    @property
    def endpoint(self) -> Optional[str]:
        return self.get_param_value("endpoint") or None

    @property
    def temperature(self) -> float:
        return float(self.get_param_value("temperature"))

    @property
    def top_p(self) -> float:
        return float(self.get_param_value("top p"))

    @property
    def max_tokens(self) -> int:
        return int(self.get_param_value("max tokens"))

    @property
    def reasoning_enabled(self) -> bool:
        return bool(self.get_param_value("reasoning"))

    @property
    def reasoning_level(self) -> str:
        level = str(self.get_param_value("reasoning level") or "medium").lower()
        return level if level in {"low", "medium", "high"} else "medium"

    @property
    def json_mode_enabled(self) -> bool:
        return bool(self.get_param_value("json mode"))

    @property
    def num_ctx(self) -> int:
        return self._param_int("num ctx")

    @property
    def reflection_enabled(self) -> bool:
        return (
            bool(self.get_param_value("reflection"))
            and self.review_speed_mode != "No additional review"
        )

    @property
    def review_speed_mode(self) -> str:
        return str(self.get_param_value("review speed mode") or "Thorough (separate passes)")

    @property
    def reflection_prompt(self) -> str:
        return self.get_param_value("reflection prompt")

    @property
    def bubble_text_shortening(self) -> str:
        return str(self.get_param_value("bubble text shortening") or "Off")

    @property
    def long_bubble_character_target(self) -> int:
        return max(self._param_int("long bubble character target", default=90), 20)

    @property
    def extreme_bubble_character_target(self) -> int:
        return max(
            self._param_int("extreme bubble character target", default=140),
            self.long_bubble_character_target,
        )

    @property
    def use_glossary_enabled(self) -> bool:
        return bool(self.get_param_value("use glossary"))

    @property
    def auto_build_glossary_enabled(self) -> bool:
        return bool(self.get_param_value("auto build glossary"))

    @property
    def glossary_refinement_enabled(self) -> bool:
        return (
            bool(self.get_param_value("glossary refinement pass"))
            and self.review_speed_mode == "Thorough (separate passes)"
        )

    def _param_int(self, param_key: str, default: int = 0) -> int:
        try:
            return max(int(float(self.get_param_value(param_key))), 0)
        except Exception:
            return default

    @property
    def previous_context_pages(self) -> int:
        return self._param_int("previous context pages")

    @property
    def include_next_context_page(self) -> bool:
        return bool(self.get_param_value("include next context page"))

    @property
    def document_context_pages(self) -> int:
        return self._param_int("document context pages")

    @property
    def context_max_characters(self) -> int:
        return self._param_int("context max characters", default=6000)

    @property
    def glossary_max_entries(self) -> int:
        return max(int(self.get_param_value("glossary max entries")), 0)

    @property
    def glossary_text(self) -> str:
        return getattr(self, "project_glossary_text", "") or ""

    @property
    def glossary_reference_text(self) -> str:
        return getattr(self, "project_glossary_reference_text", "") or ""

    @property
    def glossary_prompt(self) -> str:
        project_prompt = getattr(self, "project_glossary_prompt", "")
        if project_prompt.strip():
            return project_prompt.strip()
        return (
            "Use the glossary only as translation guidance. Apply preferred target "
            "terms naturally, but never copy glossary categories, notes, or bracketed "
            "metadata such as [CHARACTER] or [PLACE] into the translated text."
        )

    @property
    def glossary_reference_prompt(self) -> str:
        project_prompt = getattr(self, "project_glossary_reference_prompt", "")
        if project_prompt.strip():
            return project_prompt.strip()
        return (
            "Use the reference glossary as supporting context from earlier chapters or "
            "official translations. Prefer explicit project glossary entries when they conflict."
        )

    @property
    def retry_attempts(self) -> int:
        return int(self.get_param_value("retry attempts"))

    @property
    def retry_timeout(self) -> int:
        return int(self.get_param_value("retry timeout"))

    @property
    def proxy(self) -> str:
        return self.get_param_value("proxy")

    @property
    def system_prompt(self) -> str:
        return self.get_param_value("system_prompt")

    def _language_placeholder_values(self, to_lang: str = None) -> Dict[str, str]:
        source_language = self.lang_map.get(self.lang_source, self.lang_source)
        target_language = to_lang or self.lang_map.get(self.lang_target, self.lang_target)
        return {
            "source_language": source_language,
            "input_language": source_language,
            "from_lang": source_language,
            "target_language": target_language,
            "output_language": target_language,
            "to_lang": target_language,
        }

    def _render_prompt_placeholders(self, prompt: str, to_lang: str = None) -> str:
        for key, value in self._language_placeholder_values(to_lang=to_lang).items():
            prompt = prompt.replace("{" + key + "}", value)
        return prompt

    @property
    def invalid_repeat_count(self) -> int:
        return int(self.get_param_value("invalid repeat count"))

    @property
    def frequency_penalty(self) -> float:
        return float(self.get_param_value("frequency penalty"))

    @property
    def presence_penalty(self) -> float:
        return float(self.get_param_value("presence penalty"))

    @property
    def max_rpm(self) -> int:
        return int(self.get_param_value("max requests per minute"))

    @property
    def global_delay(self) -> float:
        return float(self.get_param_value("delay"))

    def set_page_context(self, imgtrans_proj=None, page_key: str = ""):
        self.context_project = imgtrans_proj
        self.context_page_key = page_key or ""

    def clear_page_context(self):
        self.context_project = None
        self.context_page_key = ""

    def _page_names_for_context(self) -> List[str]:
        project = getattr(self, "context_project", None)
        pages = getattr(project, "pages", None)
        if not isinstance(pages, dict):
            return []
        return list(pages.keys())

    def _page_context_text(self, page_name: str, include_translation: bool = True) -> str:
        project = getattr(self, "context_project", None)
        pages = getattr(project, "pages", None)
        if not isinstance(pages, dict) or page_name not in pages:
            return ""

        page_index = -1
        if hasattr(project, "pagename2idx"):
            try:
                page_index = project.pagename2idx(page_name)
            except Exception:
                page_index = -1

        source_lines = []
        translation_lines = []
        for blk in pages.get(page_name, []):
            try:
                source = blk.get_text().strip()
            except Exception:
                source = ""
            if source:
                source_lines.append(source)

            translation = getattr(blk, "translation", "")
            if include_translation and isinstance(translation, str) and translation.strip():
                translation_lines.append(translation.strip())

        if not source_lines and not translation_lines:
            return ""

        label = f"Page {page_index + 1}" if page_index >= 0 else "Page"
        chunks = [f"[{label}: {page_name}]"]
        if source_lines:
            chunks.append("Source:\n" + "\n".join(f"- {line}" for line in source_lines))
        if translation_lines:
            chunks.append(
                "Existing translation:\n"
                + "\n".join(f"- {line}" for line in translation_lines)
            )
        return "\n".join(chunks)

    def _select_document_context_pages(
        self, page_names: List[str], current_index: int, max_pages: int
    ) -> List[str]:
        if max_pages <= 0 or not page_names:
            return []
        if len(page_names) <= max_pages:
            return page_names

        half = max_pages // 2
        start = max(0, current_index - half)
        end = start + max_pages
        if end > len(page_names):
            end = len(page_names)
            start = max(0, end - max_pages)
        return page_names[start:end]

    def _truncate_context_section(self, section: str) -> str:
        max_chars = self.context_max_characters
        if max_chars <= 0 or len(section) <= max_chars:
            return section
        return section[:max_chars].rstrip() + "\n[Context truncated]"

    def _translation_context_prompt_section(self) -> str:
        page_key = getattr(self, "context_page_key", "")
        page_names = self._page_names_for_context()
        if not page_key or page_key not in page_names:
            return ""

        current_index = page_names.index(page_key)
        sections = []
        previous_count = self.previous_context_pages

        if previous_count > 0:
            previous_names = page_names[max(0, current_index - previous_count):current_index]
            previous_blocks = [
                self._page_context_text(name, include_translation=True)
                for name in previous_names
            ]
            previous_blocks = [block for block in previous_blocks if block]
            if previous_blocks:
                sections.append(
                    "PREVIOUS PAGE CONTEXT:\n" + "\n\n".join(previous_blocks)
                )

        if self.include_next_context_page and current_index + 1 < len(page_names):
            next_block = self._page_context_text(
                page_names[current_index + 1], include_translation=True
            )
            if next_block:
                sections.append("NEXT PAGE CONTEXT:\n" + next_block)

        document_count = self.document_context_pages
        if document_count > 0:
            document_names = self._select_document_context_pages(
                page_names, current_index, document_count
            )
            document_blocks = [
                self._page_context_text(name, include_translation=False)
                for name in document_names
            ]
            document_blocks = [block for block in document_blocks if block]
            if document_blocks:
                sections.append(
                    f"DOCUMENT CONTEXT (max {document_count} pages):\n"
                    + "\n\n".join(document_blocks)
                )

        if not sections:
            return ""

        context = (
            "PROJECT CONTEXT FOR CONSISTENCY ONLY:\n"
            "Use this context to keep names, references, tone, and continuity "
            "consistent. Do not translate or output these context lines unless "
            "they are part of the INPUT items.\n\n"
            + "\n\n".join(sections)
        )
        return self._truncate_context_section(context).rstrip() + "\n\n"

    def _assemble_prompts(self, queries: List[str], to_lang: str):
        from_lang = self.lang_map.get(self.lang_source, self.lang_source)

        input_elements = [
            {"id": i + 1, "source": query} for i, query in enumerate(queries)
        ]
        input_json_str = json.dumps(input_elements, ensure_ascii=False, indent=2)
        glossary_section = self._glossary_prompt_section()
        context_section = self._translation_context_prompt_section()
        shortening_section = self._bubble_text_shortening_rules()

        prompt = (
            f"Translate the following manga/comic text snippets from {from_lang} to {to_lang}. "
            "The input is a JSON array. Respond with one JSON object in the required schema.\n"
            "Preserve each id, item count, order, line intent, names, honorifics, pronouns, speaker/addressee roles, singular/plural first person, and formal/informal address. "
            "Do not turn a male character into a feminine pronoun/address, a female/girl character into a masculine pronoun/address, or I/me into we/us unless the source/context clearly says so. "
            "If gender or addressee form is unknown, keep the target wording neutral or as ambiguous as the language allows.\n\n"
            f"{shortening_section}"
            f"{context_section}"
            f"{glossary_section}"
            f"INPUT:\n{input_json_str}"
        )

        yield prompt, len(queries)

    def _glossary_prompt_section(self) -> str:
        if not self.use_glossary_enabled:
            return ""
        glossary = self.glossary_text.strip()
        reference = self.glossary_reference_text.strip()
        if not glossary and not reference:
            return ""
        sections = []
        if glossary:
            sections.append(
                "PROJECT GLOSSARY:\n"
                f"{self.glossary_prompt.strip()}\n"
                "Use project glossary entries as preferred terminology. Treat category labels, aliases, notes, confidence, gender/pronoun hints, and source comments as guidance only; never copy that metadata into the translation.\n"
                f"{glossary}"
            )
        if reference:
            sections.append(
                "REFERENCE GLOSSARY:\n"
                f"{self.glossary_reference_prompt.strip()}\n"
                "Use reference entries only as secondary consistency guidance when they do not conflict with the project glossary.\n"
                f"{reference}"
            )
        return "\n\n".join(sections) + "\n\n"

    def set_project_glossary(self, glossary):
        self.project_glossary_loaded = True
        if isinstance(glossary, dict):
            self.project_glossary_text = glossary.get("entries", "") or ""
            self.project_glossary_prompt = glossary.get("prompt", "") or ""
            self.project_glossary_reference_text = glossary.get("reference_entries", "") or ""
            self.project_glossary_reference_prompt = glossary.get("reference_prompt", "") or ""
        elif isinstance(glossary, str):
            self.project_glossary_text = glossary
            self.project_glossary_prompt = ""
            self.project_glossary_reference_text = ""
            self.project_glossary_reference_prompt = ""
        else:
            self.project_glossary_text = ""
            self.project_glossary_prompt = ""
            self.project_glossary_reference_text = ""
            self.project_glossary_reference_prompt = ""

    def get_project_glossary(self) -> Dict[str, str]:
        return {
            "entries": self.glossary_text,
            "prompt": self.glossary_prompt,
            "reference_entries": self.glossary_reference_text,
            "reference_prompt": self.glossary_reference_prompt,
        }

    def _system_prompt_with_reasoning_policy(self) -> str:
        prompt = self._render_prompt_placeholders(self.system_prompt)
        if self.reasoning_enabled:
            policy = (
                f"Use {self.reasoning_level} reasoning effort internally if the "
                "selected model supports it. Do not include reasoning, analysis, "
                "chain-of-thought, or <think> blocks in the final response; output "
                "only the requested JSON object."
            )
        else:
            policy = (
                "Do not include reasoning, analysis, chain-of-thought, or <think> "
                "blocks in the response; output only the requested JSON object."
            )
        return f"{prompt}\n\n{policy}"

    def _build_reasoning_extra_body(self) -> Dict:
        level = self.reasoning_level
        provider = self.provider
        extra_body = {}
        if self.num_ctx > 0 and provider in {"Ollama", "LLM Studio"}:
            extra_body["num_ctx"] = self.num_ctx
        if provider == "Ollama":
            extra_body["think"] = bool(self.reasoning_enabled)
            return extra_body
        if not self.reasoning_enabled:
            return extra_body
        if provider == "OpenRouter":
            extra_body["reasoning"] = {"effort": level}
        if provider == "LLM Studio":
            extra_body["reasoning"] = {"effort": level}
            extra_body["think"] = True
        if provider in ["Google", "Grok"]:
            extra_body["reasoning_effort"] = level
        return extra_body

    def _strip_reasoning_markup(self, content: str) -> str:
        cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(
            r"```(?:json)?\s*([\[{].*?[\]}])\s*```",
            lambda match: match.group(1),
            cleaned,
            flags=re.DOTALL,
        )
        return cleaned.strip()

    @staticmethod
    def _normalize_translation_entry(entry: Any, fallback_id: int = 0) -> Optional[Dict]:
        if not isinstance(entry, dict):
            return None

        normalized = dict(entry)
        if "id" not in normalized:
            return None
        try:
            normalized["id"] = int(normalized["id"])
        except (TypeError, ValueError):
            return None
        if "translation" not in normalized and "draft_translation" in normalized:
            normalized["translation"] = normalized.get("draft_translation") or ""
        if "translation" not in normalized:
            return None
        return normalized

    @classmethod
    def _normalize_translation_entries(cls, entries: List[Any], logger=None) -> List[Dict]:
        normalized_entries = []
        dropped = 0
        for idx, item in enumerate(entries):
            normalized = cls._normalize_translation_entry(item, idx + 1)
            if normalized is None:
                dropped += 1
                continue
            normalized_entries.append(normalized)
        if dropped and logger is not None:
            logger.warning(f"Dropped {dropped} translation entries without usable id or translation.")
        return normalized_entries

    @classmethod
    def _normalize_translation_response_data(cls, data: Any, logger=None) -> Any:
        if isinstance(data, dict) and not data:
            if logger is not None:
                logger.warning(
                    "LLM returned empty JSON object; falling back to draft translations where possible."
                )
            return {"translations": []}

        if isinstance(data, list):
            return {
                "translations": cls._normalize_translation_entries(data, logger)
            }

        if not isinstance(data, dict):
            return data

        if "translations" in data:
            translations = data.get("translations")
            if translations is None:
                translations = []
            elif isinstance(translations, dict):
                translations = [translations]
            elif not isinstance(translations, list):
                return data
            normalized = dict(data)
            normalized["translations"] = cls._normalize_translation_entries(translations, logger)
            return normalized

        if all(isinstance(key, str) and key.isdigit() for key in data.keys()):
            return {
                "translations": [
                    {"id": int(key), "translation": value}
                    for key, value in data.items()
                ]
            }

        if "id" in data and (
            "translation" in data
            or "draft_translation" in data
        ):
            normalized = cls._normalize_translation_entry(data, 1)
            return {"translations": [normalized] if normalized else []}

        return data

    @classmethod
    def _normalize_glossary_response_data(cls, data: Any, logger=None) -> Any:
        def normalize_entry(entry: Any) -> Any:
            if not isinstance(entry, dict):
                return entry
            normalized_entry = dict(entry)
            if "notes" in normalized_entry and "note" not in normalized_entry:
                normalized_entry["note"] = normalized_entry.get("notes") or ""
            aliases = normalized_entry.get("aliases", [])
            if isinstance(aliases, str):
                aliases = [
                    alias.strip()
                    for alias in re.split(r"[,|;/]", aliases)
                    if alias.strip()
                ]
            elif not isinstance(aliases, list):
                aliases = []
            normalized_entry["aliases"] = [
                str(alias).strip() for alias in aliases if str(alias).strip()
            ]
            normalized_entry["category"] = canonicalize_glossary_category(
                normalized_entry.get("category", "")
            )
            return normalized_entry

        def normalize_entries(entries: Any) -> List[Any]:
            if entries is None:
                return []
            if isinstance(entries, dict):
                entries = [entries]
            if isinstance(entries, list):
                return [normalize_entry(entry) for entry in entries]
            return entries

        if isinstance(data, dict) and not data:
            if logger is not None:
                logger.warning("LLM returned empty glossary JSON object; no glossary entries were extracted.")
            return {"entries": []}

        if isinstance(data, list):
            return {"entries": normalize_entries(data)}

        if not isinstance(data, dict):
            return data

        if "entries" in data:
            normalized = dict(data)
            normalized["entries"] = normalize_entries(data.get("entries"))
            return normalized

        for key in ("glossary", "terms", "items"):
            entries = data.get(key)
            if isinstance(entries, list):
                return {"entries": normalize_entries(entries)}

        if "source" in data and "target" in data:
            return {"entries": normalize_entries([data])}

        return data

    def _build_reflection_prompt(
        self, original_prompt: str, draft_response: TranslationResponse
    ) -> str:
        draft_json = draft_response.model_dump_json(indent=2)
        expected_ids = [item.id for item in draft_response.translations]
        glossary_section = ""
        if self.review_speed_mode != "Reflection only (fastest)":
            glossary_section = self._review_glossary_prompt_section()
        combined_instruction = ""
        if self.review_speed_mode == "Combined review (fast)":
            combined_instruction = (
                "Apply the active glossary during this same review pass; "
                "this pass replaces a dedicated glossary-refinement request.\n"
            )
        return (
            f"{self._render_prompt_placeholders(self.reflection_prompt)}\n\n"
            f"{self._review_quality_rules(len(draft_response.translations), expected_ids)}"
            f"{combined_instruction}"
            f"{glossary_section}"
            "ORIGINAL TRANSLATION TASK:\n"
            f"{original_prompt}\n\n"
            "DRAFT TRANSLATION JSON:\n"
            f"{draft_json}\n\n"
            "Return JSON only with the TranslationResponse schema: "
            '{"translations":[{"id":1,"translation":"Reviewed translation"}]}.'
        )

    def _build_manual_review_prompt(
        self, expected_items: List[Dict[str, Any]], to_lang: str
    ) -> str:
        expected_ids = [item["id"] for item in expected_items]
        from_lang = self.lang_map.get(self.lang_source, self.lang_source)
        return (
            f"Review and correct existing translations from {from_lang} to {to_lang}.\n"
            "Return valid JSON only. No markdown. No explanations. No comments. Never return {}.\n"
            'Use exactly this schema: { "translations": [ {"id": 1, "translation": "reviewed translation"} ] }\n'
            f"Return exactly {len(expected_items)} items with these IDs: {expected_ids}.\n"
            "Preserve every id exactly. Do not add, remove, reorder, merge, or split items.\n"
            "Use source text to catch mistranslations, missing meaning, wrong pronouns, wrong names, and inconsistent address forms.\n"
            "If the current translation is already good, return it unchanged.\n"
            "If unsure, return the current translation unchanged.\n"
            "Keep the same target language.\n"
            "Do not include source, draft_translation, category labels, glossary metadata, notes, or comments in the final output.\n\n"
            f"{self._review_quality_rules(len(expected_items), expected_ids)}"
            f"{self._translation_context_prompt_section()}"
            f"{self._review_glossary_prompt_section()}"
            f"INPUT:\n{json.dumps(expected_items, ensure_ascii=False, indent=2)}"
        )

    def review_translations(self, src_list: List[str], draft_list: List[str]) -> List[str]:
        if not src_list:
            return []

        to_lang = self.lang_map.get(self.lang_target, self.lang_target)
        expected_items = [
            {"id": i + 1, "source": source, "draft_translation": draft}
            for i, (source, draft) in enumerate(zip(src_list, draft_list))
        ]
        chunk_size = 20
        items_by_id: Dict[int, str] = {}
        for chunk in (
            expected_items[i : i + chunk_size]
            for i in range(0, len(expected_items), chunk_size)
        ):
            prompt = self._build_manual_review_prompt(chunk, to_lang)
            expected_ids = [item["id"] for item in chunk]
            response = self._request_translation(
                prompt,
                is_reflection=True,
                purpose="manual_review",
                expected_count=len(chunk),
                expected_ids=expected_ids,
                max_tokens_override=min(max(self.max_tokens, 2048), 8192),
            )
            if response is not None:
                response = self._clean_translation_response(response)
                for item in response.translations:
                    if item.id not in items_by_id and item.translation:
                        items_by_id[item.id] = item.translation
        return [
            items_by_id.get(item["id"], item.get("draft_translation") or item.get("source") or "")
            for item in expected_items
        ]

    def _canonical_glossary_category(self, category: str) -> str:
        return canonicalize_glossary_category(category)

    def _enabled_auto_glossary_categories(self) -> Dict[str, str]:
        enabled = {}
        for category, config in AUTO_GLOSSARY_CATEGORY_CONFIG.items():
            param_key = config["param"]
            try:
                if bool(self.get_param_value(param_key)):
                    enabled[category] = config["label"]
            except Exception:
                continue
        return enabled

    def _auto_glossary_category_prompt(self) -> str:
        enabled = self._enabled_auto_glossary_categories()
        if not enabled:
            return "No automatic glossary categories are enabled. Return an empty entries list."

        category_lines = [
            f"- {category}: {label}"
            for category, label in enabled.items()
        ]
        disabled = [
            category for category in AUTO_GLOSSARY_CATEGORY_CONFIG
            if category not in enabled
        ]
        return (
            "Only extract entries from these enabled categories:\n"
            + "\n".join(category_lines)
            + "\nUse the category value exactly as listed above. "
            "If a candidate does not clearly match an enabled category, omit it."
            + (
                "\nDisabled categories must be ignored: "
                + ", ".join(disabled)
                + "."
                if disabled
                else ""
            )
        )

    def _review_quality_rules(self, expected_count: int, expected_ids: List[int]) -> str:
        return (
            "REVIEW REQUIREMENTS:\n"
            "- JSON only. Do not output explanations, markdown, comments, source text, draft_translation, or glossary metadata.\n"
            "- Use the TranslationResponse schema exactly: {\"translations\":[{\"id\":1,\"translation\":\"reviewed translation\"}]}.\n"
            f"- Return exactly {expected_count} items with the same IDs: {expected_ids}.\n"
            "- Keep the same IDs, keep the same item count, and do not reorder, merge, add, or omit items.\n"
            "- If a draft translation is already correct, return it unchanged.\n"
            "- Check pronoun consistency against the available source and context.\n"
            "- Explicitly verify that male characters are not translated with feminine pronouns/address, female or girl characters are not translated with masculine pronouns/address, and a singular speaker is not changed into we/us/our.\n"
            "- Check speaker and addressee references, including whether first person and second person are preserved.\n"
            "- Do not change I/me/my into we/us/our unless the source clearly means plural first person.\n"
            "- Do not change you into they/he/she or the wrong form of address unless the source clearly requires it.\n"
            "- Check address forms and honorifics such as Mr./Ms., Herr/Frau, du/Sie, and similar forms when context or glossary supports them.\n"
            "- If gender, pronouns, or social address are unknown, do not invent that information.\n"
            "- Use glossary names, aliases, titles, and honorifics as guidance only; never write category labels, aliases, notes, confidence, or other metadata into translations.\n\n"
            f"{self._bubble_text_shortening_rules()}"
        )

    def _bubble_text_shortening_rules(self) -> str:
        mode = self.bubble_text_shortening
        if mode == "Off":
            return ""
        long_target = self.long_bubble_character_target
        extreme_target = self.extreme_bubble_character_target
        if mode == "Shorten long and extremely long translations":
            instruction = (
                f"- If a translation is longer than about {long_target} characters, "
                "rewrite it into concise comic dialogue when possible.\n"
            )
        else:
            instruction = ""
        return (
            "SPEECH-BUBBLE LENGTH GUIDANCE:\n"
            f"{instruction}"
            f"- If a translation is longer than about {extreme_target} characters, aggressively condense phrasing to fit a speech bubble while preserving all essential meaning.\n"
            "- Prefer natural contractions, remove redundant wording, and avoid explanatory additions; never delete plot-critical facts, names, commands, or emotional intent only to meet a target.\n\n"
        )

    def _review_glossary_entries(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        stats: Dict[str, Any] = {
            "duplicates": 0,
            "conflicts": 0,
            "categories": set(),
            "enabled": False,
        }
        if not self.use_glossary_enabled:
            return [], stats
        entries = self._parse_glossary_entries()
        if not entries:
            return [], stats

        compact_entries: List[Dict[str, Any]] = []
        seen_terms: Set[Tuple[str, str]] = set()
        for entry in entries:
            category = self._canonical_glossary_category(entry.get("category", ""))
            if category not in REVIEW_GLOSSARY_CATEGORIES:
                continue
            terms = {
                self._normalize_glossary_term(entry.get("source", "")),
                self._normalize_glossary_term(entry.get("target", "")),
                *[
                    self._normalize_glossary_term(alias)
                    for alias in entry.get("aliases", [])
                ],
            }
            terms.discard("")
            duplicate = any((category, term) in seen_terms for term in terms)
            if duplicate:
                stats["duplicates"] += 1
                stats["conflicts"] += 1
                continue
            compact = dict(entry)
            compact["category"] = category
            compact_entries.append(compact)
            stats["categories"].add(category)
            for term in terms:
                seen_terms.add((category, term))

        stats["enabled"] = bool(compact_entries)
        return compact_entries, stats

    def _review_glossary_prompt_section(self) -> str:
        entries, stats = self._review_glossary_entries()
        logger = getattr(self, "logger", None)
        if not entries:
            if logger is not None:
                logger.info("Review glossary guidance disabled or no relevant entries found.")
            return ""

        max_entries = self.glossary_max_entries or len(entries)
        entries = entries[:max_entries]
        categories = sorted(stats["categories"])
        if logger is not None:
            logger.info(
                "Review glossary guidance enabled: entries=%s categories=%s duplicates=%s conflicts=%s"
                % (
                    len(entries),
                    ", ".join(categories),
                    stats["duplicates"],
                    stats["conflicts"],
                )
            )

        lines = []
        for entry in entries:
            parts = [
                f"- [{entry['category']}] {entry['source']} -> {entry['target']}"
            ]
            aliases = entry.get("aliases") or []
            note = entry.get("note") or ""
            if aliases:
                parts.append("aliases: " + ", ".join(aliases))
            if note:
                parts.append("notes: " + note)
            lines.append("; ".join(parts))

        return (
            "RELEVANT GLOSSARY FOR REVIEW:\n"
            "Use these entries to keep character names, aliases, titles, honorifics, places, and organizations consistent. "
            "Aliases should be normalized to the preferred target. Use honorifics and titles only when natural and supported by context. "
            "Do not output category labels, aliases, notes, confidence, or glossary metadata.\n"
            + "\n".join(lines)
            + "\n\n"
        )

    def _format_glossary_entry(
        self, entry: GlossaryEntry, category: Optional[str] = None
    ) -> str:
        category = category or self._canonical_glossary_category(entry.category)
        note = (entry.note or "").strip()
        aliases = [alias.strip() for alias in (entry.aliases or []) if alias.strip()]
        if aliases and not self._extract_aliases_from_note(note):
            alias_note = "aliases: " + ", ".join(aliases)
            note = f"{note}; {alias_note}" if note else alias_note
        line = f"{entry.source.strip()} => {entry.target.strip()} [{category}]"
        if note:
            line = f"{line} # {note}"
        return line

    def _normalize_glossary_term(self, value: str) -> str:
        value = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
        value = re.sub(r"[\s\-_.'\"`´’‘“”、。・/\\|]+", "", value)
        return value

    def _fold_kana_for_glossary_filter(self, value: str) -> str:
        text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
        folded = []
        for char in text:
            code = ord(char)
            if 0x30A1 <= code <= 0x30F6:
                folded.append(chr(code - 0x60))
            else:
                folded.append(char)
        return "".join(folded)

    def _compact_glossary_source(self, value: str) -> str:
        text = self._fold_kana_for_glossary_filter(value)
        text = re.sub(r"[\s\t\r\n!！?？。｡、,.，…・･♪♡❤（）()\[\]{}「」『』\"'`´“”‘’:：;；]+", "", text)
        text = re.sub(r"[ー〜～~]+", "", text)
        text = re.sub(r"[っッ]+$", "", text)
        return text

    def _compact_glossary_target(self, value: str) -> str:
        text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
        return re.sub(r"[\s\-_.'\"`´’‘“”!?]+", "", text)

    def _glossary_punctuation_only(self, value: str) -> bool:
        text = unicodedata.normalize("NFKC", str(value or "")).strip()
        if not text:
            return False
        return not any(char.isalnum() for char in text)

    def _glossary_is_interjection_or_sfx(self, source: str, target: str) -> bool:
        if self._compact_glossary_source(source) in GLOSSARY_INTERJECTION_STEMS:
            return True
        if self._compact_glossary_target(target) in GLOSSARY_REACTION_TARGETS:
            return True
        return False

    def _glossary_has_japanese_honorific(self, source: str) -> bool:
        source_norm = self._fold_kana_for_glossary_filter(source)
        source_norm = re.sub(r"[!！?？。｡、,.，…・･♪♡❤（）()\[\]{}「」『』\"'`´“”‘’:：;；\s]+$", "", source_norm)
        if re.search(r"さ[〜～ー-]*ん$", source_norm):
            return True
        return any(source_norm.endswith(honorific) for honorific in GLOSSARY_JA_HONORIFICS)

    def _glossary_looks_like_japanese_name(self, source: str) -> bool:
        source_norm = self._fold_kana_for_glossary_filter(source)
        source_norm = re.sub(r"[\s!！?？。｡、,.，…・･♪♡❤（）()\[\]{}「」『』\"'`´“”‘’:：;；]+", "", source_norm)
        source_norm = re.sub(r"[〜～ー-]+$", "", source_norm)
        if not source_norm:
            return False
        if self._glossary_has_japanese_honorific(source):
            return True
        if re.fullmatch(r"[\u4e00-\u9fff]{1,6}", source_norm):
            return True
        if 2 <= len(source_norm) <= 8 and re.fullmatch(r"[\u3040-\u309f\u30a0-\u30ffー〜～]+", source_norm):
            return source_norm not in GLOSSARY_INTERJECTION_STEMS
        return False

    def _glossary_looks_like_latin_name(self, value: str) -> bool:
        text = unicodedata.normalize("NFKC", str(value or "")).strip()
        text = re.sub(r"[!！?？。｡、,.，…]+$", "", text)
        if self._compact_glossary_target(text) in GLOSSARY_REACTION_TARGETS:
            return False
        return bool(re.fullmatch(r"[A-Z][A-Za-z'’-]{1,30}(?:\s+[A-Z][A-Za-z'’-]{1,30}){0,3}", text))

    def _glossary_looks_like_name_candidate(self, source: str, target: str) -> bool:
        return (
            self._glossary_looks_like_japanese_name(source)
            or self._glossary_looks_like_latin_name(source)
            or self._glossary_looks_like_latin_name(target)
        )

    def _glossary_source_sentence_like(self, source: str, category: str) -> bool:
        if category == "character" and self._glossary_looks_like_name_candidate(source, ""):
            return False
        source_norm = self._fold_kana_for_glossary_filter(source)
        compact = self._compact_glossary_source(source)
        if re.search(r"[?？]", source_norm):
            return True
        if re.search(r"[。｡!！]", source_norm) and len(compact) > 3:
            return True
        if any(pattern in source_norm for pattern in GLOSSARY_DIALOGUE_SOURCE_PATTERNS):
            return True
        if re.search(r"(ます|です|した|して|する|たい|ない|だよ|だね|だな)$", source_norm):
            return True
        if len(compact) > 3 and re.search(r"(よ|ね|か|や)$", source_norm):
            return True
        return False

    def _glossary_target_sentence_like(self, target: str) -> bool:
        target_norm = unicodedata.normalize("NFKC", str(target or "")).strip()
        if re.search(r"[?？]", target_norm):
            return True
        if re.match(r"(?i)^(can|could|would|will|you|you'll|this|that|it|i|we)\b", target_norm):
            return True
        words = re.findall(r"[A-Za-z0-9']+", target_norm)
        if len(words) > 4:
            return True
        if re.search(r"[.!！]", target_norm) and self._compact_glossary_target(target_norm) not in GLOSSARY_REACTION_TARGETS:
            return len(words) > 1
        return False

    def _glossary_title_candidate_valid(self, source: str, target: str) -> bool:
        if self._glossary_source_sentence_like(source, "title") or self._glossary_target_sentence_like(target):
            return False
        if self._glossary_is_interjection_or_sfx(source, target):
            return False
        source_norm = self._fold_kana_for_glossary_filter(source)
        target_norm = unicodedata.normalize("NFKC", str(target or "")).casefold()
        if any(marker in source_norm for marker in GLOSSARY_TITLE_SOURCE_MARKERS):
            return True
        if any(marker in target_norm for marker in GLOSSARY_TITLE_TARGET_MARKERS):
            return True
        if re.search(r"第\s*\d+|#\s*\d+", source_norm) or re.search(r"chapter\s+\d+|episode\s+\d+|volume\s+\d+", target_norm):
            return True
        return False

    def _glossary_entry_rejection_reason(self, entry: GlossaryEntry, category: str) -> Optional[str]:
        source = entry.source.strip()
        target = entry.target.strip()
        if not source or not target:
            return "empty_source_or_target"
        if self._glossary_punctuation_only(source) or self._glossary_punctuation_only(target):
            return "punctuation_only"
        if category == "character":
            if self._glossary_is_interjection_or_sfx(source, target):
                return "interjection_or_sfx"
            if self._glossary_source_sentence_like(source, category) or self._glossary_target_sentence_like(target):
                return "sentence_like"
            if entry.confidence < 0.5 and not self._glossary_looks_like_name_candidate(source, target):
                return "sentence_like"
        elif category == "title":
            if not self._glossary_title_candidate_valid(source, target):
                return "invalid_title"
        return None

    def _log_glossary_rejection(self, source: str, target: str, category: str, reason: str):
        self.logger.info(
            f'Glossary rejected entry: source="{source}" target="{target}" category={category} reason={reason}'
        )

    def _extract_aliases_from_note(self, note: str) -> List[str]:
        if not note:
            return []
        match = re.search(r"(?:^|;)\s*(?:aliases?|aka)\s*[:=]\s*([^;#]+)", note, flags=re.IGNORECASE)
        if not match:
            return []
        return [
            alias.strip()
            for alias in re.split(r"[,|/]", match.group(1))
            if alias.strip()
        ]

    def _parse_glossary_entry_line(self, line: str) -> Optional[Dict[str, Any]]:
        clean = line.strip()
        if not clean or clean.startswith("#") or "=>" not in clean:
            return None
        source, remainder = clean.split("=>", 1)
        source = source.strip()
        if not source:
            return None
        target_part = remainder.strip()
        note = ""
        if "#" in target_part:
            target_part, note = target_part.split("#", 1)
            note = note.strip()
        category = "term"
        match = re.search(r"\[([^\]]+)\]\s*$", target_part)
        if match:
            category = self._canonical_glossary_category(match.group(1))
            target_part = target_part[: match.start()].strip()
        target = target_part.strip()
        if not target:
            return None
        return {
            "source": source,
            "target": target,
            "category": category,
            "aliases": self._extract_aliases_from_note(note),
            "note": note,
            "line": clean,
        }

    def _parse_glossary_entries(self) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        combined = "\n".join(
            part for part in (self.glossary_text, self.glossary_reference_text) if part
        )
        for line in combined.splitlines():
            entry = self._parse_glossary_entry_line(line)
            if entry is not None:
                entries.append(entry)
        return entries

    def _parse_glossary_lines(self) -> Dict[str, str]:
        entries = {}
        for entry in self._parse_glossary_entries():
            entries[entry["source"]] = entry["line"]
        return entries

    def _save_glossary_entries(self, entries: List[GlossaryEntry]) -> int:
        if not entries or self.glossary_max_entries == 0:
            return 0

        enabled_categories = self._enabled_auto_glossary_categories()
        if not enabled_categories:
            return 0

        stats = {
            "raw": len(entries),
            "normalized": 0,
            "recognized_names": 0,
            "added": 0,
            "added_names": 0,
            "deduplicated": 0,
            "rejected": 0,
            "conflicts": 0,
        }
        rejection_reasons: Dict[str, int] = {}
        existing_entries = self._parse_glossary_entries()
        glossary_lines = [entry["line"] for entry in existing_entries]
        seen_terms: Set[Tuple[str, str]] = set()
        seen_sources: Set[str] = set()

        def reject(source: str, target: str, category: str, reason: str):
            stats["rejected"] += 1
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
            self._log_glossary_rejection(source, target, category, reason)

        for existing in existing_entries:
            category = existing["category"]
            source_norm = self._normalize_glossary_term(existing["source"])
            if source_norm:
                seen_sources.add(source_norm)
                seen_terms.add((category, source_norm))
            if category in {"character", "honorific", "title", "place", "organization"}:
                target_norm = self._normalize_glossary_term(existing["target"])
                if target_norm:
                    seen_terms.add((category, target_norm))
            for alias in existing.get("aliases", []):
                alias_norm = self._normalize_glossary_term(alias)
                if alias_norm:
                    seen_terms.add((category, alias_norm))

        for entry in entries:
            source = entry.source.strip()
            target = entry.target.strip()
            category = self._canonical_glossary_category(entry.category)
            stats["normalized"] += 1
            if category == "character":
                stats["recognized_names"] += 1
            if not source or not target:
                reject(source, target, category, "empty_source_or_target")
                continue
            if category not in enabled_categories:
                reject(source, target, category, "category_disabled")
                continue
            reason = self._glossary_entry_rejection_reason(entry, category)
            if reason is not None:
                reject(source, target, category, reason)
                continue
            candidate_terms = {
                self._normalize_glossary_term(source),
                *[
                    self._normalize_glossary_term(alias)
                    for alias in (entry.aliases or [])
                ],
            }
            if category in {"character", "honorific", "title", "place", "organization"}:
                candidate_terms.add(self._normalize_glossary_term(target))
            candidate_terms.discard("")
            if not candidate_terms:
                reject(source, target, category, "empty_source_or_target")
                continue
            source_norm = self._normalize_glossary_term(source)
            duplicate_keys = {
                term for term in candidate_terms if (category, term) in seen_terms
            }
            if source_norm in seen_sources or duplicate_keys:
                stats["deduplicated"] += 1
                stats["conflicts"] += 1
                reject(source, target, category, "duplicate")
                continue
            glossary_lines.append(self._format_glossary_entry(entry, category=category))
            stats["added"] += 1
            if category == "character":
                stats["added_names"] += 1
            if source_norm:
                seen_sources.add(source_norm)
            for term in candidate_terms:
                seen_terms.add((category, term))

        limited_lines = glossary_lines[-self.glossary_max_entries :]
        self.project_glossary_text = "\n".join(limited_lines)
        self.project_glossary_loaded = True
        self.logger.info(
            "Glossary extraction stats: raw=%s normalized=%s accepted=%s recognized_names=%s added_names=%s deduplicated=%s rejected=%s conflicts=%s rejection_reasons=%s"
            % (
                stats["raw"],
                stats["normalized"],
                stats["added"],
                stats["recognized_names"],
                stats["added_names"],
                stats["deduplicated"],
                stats["rejected"],
                stats["conflicts"],
                rejection_reasons,
            )
        )
        return stats["added"]

    def _build_glossary_extraction_prompt(
        self, src_list: List[str], translations: List[str], to_lang: str
    ) -> str:
        from_lang = self.lang_map.get(self.lang_source, self.lang_source)
        pairs = [
            {"id": i + 1, "source": source, "draft_translation": translation}
            for i, (source, translation) in enumerate(zip(src_list, translations))
        ]
        existing_glossary = self.glossary_text.strip() or "(empty)"
        reference_glossary = self.glossary_reference_text.strip()
        reference_section = (
            f"\n\nREFERENCE GLOSSARY:\n{self.glossary_reference_prompt.strip()}\n{reference_glossary}"
            if reference_glossary and self.use_glossary_enabled
            else ""
        )
        category_prompt = self._auto_glossary_category_prompt()
        return (
            f"Extract a reusable translation glossary from {from_lang} to {to_lang}.\n"
            f"{category_prompt}\n"
            "The draft_translation field may contain an official/reference translation, "
            "a previous project translation, or the source text when no translation is available. "
            "Prefer official/reference spellings when present.\n"
            "Strict category rules:\n"
            "- character: only real person/character names from source and draft_translation. "
            "Names with honorifics are allowed, including ちゃん, くん, さん, 先輩, 先生, and 様; "
            "keep honorific variants as aliases or short notes when useful. "
            "Use category \"character\" for character/person names; do not use category \"name\".\n"
            "- title: only real titles, roles, works, chapter/series titles, job titles, or ranks. "
            "Do not classify questions, commands, reactions, or ordinary dialogue as title.\n"
            "- Do not add generic words, ordinary phrases, one-off dialogue, common pronouns, ordinary address words, or style notes.\n"
            "- Keep gender/pronoun information only as notes for disambiguation when it is clearly supported by the source or translations; do not invent it.\n"
            "- Do not classify interjections, moans, sound effects, punctuation, or normal dialogue as names or titles.\n"
            "- Do not add entries like Ah, Ahh, Huh, Hmph, Tsk, Ugh, Hehe, Sorry, Wait, Yes, No, or Oh as names.\n"
            "- Reject source strings that are punctuation-only, almost empty, sentence-like, a full sentence, a question, or a command.\n"
            "- If unsure whether something is a real name/title, omit it.\n"
            "- Do not invent names, aliases, genders, pronouns, or relationships. Alternative romanizations or spellings may be aliases.\n\n"
            "Return JSON only with the GlossaryResponse schema: "
            '{"entries":[{"source":"原文名","target":"Preferred translated name","category":"character|place|organization|title|term|honorific|catchphrase","aliases":[],"notes":"optional short note","confidence":0.5}]}. '
            "Never return {}. If no valid entries are found, return {\"entries\":[]}. "
            "Each entry must contain source, target, category, aliases, notes, and confidence. "
            "Category, aliases, notes, and confidence are metadata for the glossary only; they must never be copied into translations.\n\n"
            f"EXISTING GLOSSARY:\n{existing_glossary}"
            f"{reference_section}\n\n"
            f"TRANSLATION PAIRS:\n{json.dumps(pairs, ensure_ascii=False, indent=2)}"
        )

    def _update_glossary_from_batch(
        self, src_list: List[str], translations: List[str], to_lang: str, force: bool = False
    ) -> int:
        if (not force and not self.auto_build_glossary_enabled) or not src_list:
            return 0
        if not self._enabled_auto_glossary_categories():
            return 0

        system_prompt = (
            "You extract concise translation glossaries. Return only valid JSON "
            'matching the GlossaryResponse schema: {"entries":[{"source":"原文名",'
            '"target":"Preferred translated name","category":"character|place|organization|title|term|honorific|catchphrase","aliases":[],'
            '"notes":"optional short note","confidence":0.5}]}. Never return {}. '
            'If no valid glossary entries exist, return {"entries":[]}. '
            "Do not invent names. Do not classify interjections, moans, sound effects, punctuation, "
            "questions, commands, or normal dialogue as names or titles."
        )
        prompt = self._build_glossary_extraction_prompt(src_list, translations, to_lang)
        try:
            response = self._request_model_object(
                prompt,
                GlossaryResponse,
                system_prompt,
                purpose="glossary",
                expected_count=len(src_list),
                expected_ids=list(range(1, len(src_list) + 1)),
            )
            if isinstance(response, GlossaryResponse):
                saved_count = self._save_glossary_entries(response.entries)
                if saved_count:
                    self.logger.info(
                        f"Glossary updated with {saved_count} extracted entries."
                    )
                return saved_count
        except Exception as e:
            self.logger.warning(
                f"Glossary extraction failed; continuing without glossary update. {type(e).__name__}: {e}"
            )
        return 0

    def _build_glossary_refinement_prompt(
        self, src_list: List[str], translations: List[str], to_lang: str
    ) -> str:
        from_lang = self.lang_map.get(self.lang_source, self.lang_source)
        items = [
            {"id": i + 1, "source": source, "translation": translation}
            for i, (source, translation) in enumerate(zip(src_list, translations))
        ]
        return (
            f"Revise the translations from {from_lang} to {to_lang} using the glossary.\n"
            f"{self._review_quality_rules(len(items), [item['id'] for item in items])}"
            "Only change text where the glossary improves consistency. Preserve "
            "meaning, tone, line count, ids, and natural target-language grammar. "
            "Correct inconsistent character names by normalizing aliases to the preferred target. "
            "Honorifics and titles should be used only when natural and supported by context. "
            "Return only JSON in the required translation schema.\n\n"
            f"{self._translation_context_prompt_section()}"
            f"{self._review_glossary_prompt_section()}"
            f"TRANSLATIONS TO REVIEW:\n{json.dumps(items, ensure_ascii=False, indent=2)}"
        )

    def _clean_glossary_metadata_from_translation(self, text: str) -> str:
        if not isinstance(text, str) or "[" not in text:
            return text
        categories = (
            "character",
            "place",
            "organization",
            "organisation",
            "title",
            "term",
            "name",
            "person",
            "item",
            "location",
            "nickname",
            "honorific",
            "catchphrase",
            "phrase",
        )
        pattern = r"\s*\[(?:" + "|".join(categories) + r")\]\s*"
        return re.sub(pattern, " ", text, flags=re.IGNORECASE).strip()

    def _clean_translation_response(self, response: Optional[TranslationResponse]) -> Optional[TranslationResponse]:
        if response is None:
            return None
        for item in response.translations:
            item.translation = self._clean_glossary_metadata_from_translation(item.translation)
        return response

    def _refine_translations_with_glossary(
        self, src_list: List[str], translations: List[str], to_lang: str
    ) -> List[str]:
        if (
            not self.glossary_refinement_enabled
            or not self.use_glossary_enabled
            or not self.glossary_text.strip()
            or not src_list
        ):
            return translations

        prompt = self._build_glossary_refinement_prompt(src_list, translations, to_lang)
        try:
            response = self._request_translation(
                prompt,
                is_reflection=True,
                purpose="glossary",
                expected_count=len(src_list),
                expected_ids=list(range(1, len(src_list) + 1)),
            )
            if response and len(response.translations) == len(src_list):
                response = self._clean_translation_response(response)
                translations_by_id = {
                    item.id: item.translation for item in response.translations
                }
                self.logger.info("Glossary refinement pass completed.")
                return [
                    translations_by_id.get(i, translations[i - 1])
                    for i in range(1, len(src_list) + 1)
                ]
            self.logger.warning("Glossary refinement returned an invalid translation count.")
        except Exception as e:
            self.logger.warning(
                f"Glossary refinement failed; using previous translation. {type(e).__name__}: {e}"
            )
        return translations

    def _record_usage(self, completion):
        if hasattr(completion, "usage") and completion.usage:
            self.token_count += completion.usage.total_tokens
            self.token_count_last = completion.usage.total_tokens
        else:
            self.token_count_last = 0

    def _request_model_object(
        self,
        prompt: str,
        response_model: Type[BaseModel],
        system_prompt: str,
        purpose: str = "translation",
        expected_count: Optional[int] = None,
        expected_ids: Optional[List[int]] = None,
    ) -> Optional[BaseModel]:
        current_api_key = self._select_api_key()

        if not current_api_key:
            if self.provider in ["LLM Studio", "Ollama"]:
                current_api_key = "dummy-key"
            else:
                raise ConnectionError("No available API key found.")

        if self.provider == "LLM Studio" and not self.endpoint:
            raise ValueError(
                "Endpoint must be specified when using the LLM Studio provider (e.g., http://localhost:1234/v1)."
            )

        if not self._initialize_client(current_api_key):
            raise ConnectionError("Failed to initialize API client.")

        self._respect_delay()

        model_name = self.override_model or self.model
        if ": " in model_name:
            model_name = model_name.split(": ", 1)[1]

        api_args = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
        }

        if self.json_mode_enabled and self.provider == "LLM Studio":
            api_args["response_format"] = {
                "type": "json_schema",
                "json_schema": {"schema": response_model.model_json_schema()},
            }
        elif self.json_mode_enabled and self.provider in ["OpenAI", "Grok", "Google", "OpenRouter", "Ollama"]:
            api_args["response_format"] = {"type": "json_object"}

        if self.provider == "OpenAI":
            api_args["frequency_penalty"] = self.frequency_penalty
            api_args["presence_penalty"] = self.presence_penalty
            if self.reasoning_enabled:
                api_args["reasoning_effort"] = self.reasoning_level

        extra_body = self._build_reasoning_extra_body()
        if extra_body:
            api_args["extra_body"] = extra_body

        json_mode = api_args.get("response_format", {}).get("type", "none")
        self.logger.info(
            "LLM request purpose=%s provider=%s model=%s json_mode=%s reasoning=%s "
            "think=%s num_ctx=%s max_tokens=%s expected_count=%s expected_ids=%s prompt_length=%s"
            % (
                purpose,
                self.provider,
                model_name,
                json_mode,
                self.reasoning_enabled,
                extra_body.get("think") if isinstance(extra_body, dict) else None,
                extra_body.get("num_ctx") if isinstance(extra_body, dict) else None,
                self.max_tokens,
                expected_count,
                expected_ids,
                len(prompt),
            )
        )

        completion = self._create_completion(api_args)
        self._record_usage(completion)

        if not (
            completion.choices
            and completion.choices[0].message
            and completion.choices[0].message.content
        ):
            return None

        raw_content = completion.choices[0].message.content
        json_to_parse = self._strip_reasoning_markup(raw_content)
        start = json_to_parse.find("{")
        end = json_to_parse.rfind("}")
        if start != -1 and end != -1 and end > start:
            json_to_parse = json_to_parse[start : end + 1]
        else:
            start = json_to_parse.find("[")
            end = json_to_parse.rfind("]")
            if start != -1 and end != -1 and end > start:
                json_to_parse = json_to_parse[start : end + 1]

        raw_data = json.loads(json_to_parse)
        self.logger.debug(f"Raw JSON content from API: {raw_content}")
        if response_model is GlossaryResponse:
            raw_data = self._normalize_glossary_response_data(raw_data, self.logger)
            self.logger.debug(f"Normalized glossary JSON content from API: {raw_data}")
        return response_model.model_validate(raw_data)

    def _create_completion(self, api_args: Dict):
        if self.provider == "Ollama":
            return self._create_ollama_completion(api_args)
        try:
            return self.client.chat.completions.create(**api_args)
        except openai.BadRequestError as e:
            retry_args = dict(api_args)
            changed = False

            if "max_tokens" in retry_args:
                retry_args["max_completion_tokens"] = retry_args.pop("max_tokens")
                changed = True

            for key in [
                "temperature",
                "top_p",
                "frequency_penalty",
                "presence_penalty",
            ]:
                if key in retry_args:
                    retry_args.pop(key)
                    changed = True

            if "extra_body" in retry_args:
                retry_args.pop("extra_body")
                changed = True
                self.logger.warning(
                    "Provider rejected request options; retrying without provider-specific reasoning/think controls."
                )

            if not changed:
                raise

            self.logger.warning(
                "Request was rejected by the provider. Retrying with reasoning-model compatible arguments."
            )
            try:
                return self.client.chat.completions.create(**retry_args)
            except Exception:
                raise e

    def _ollama_chat_endpoint(self) -> str:
        endpoint = (self.endpoint or "http://localhost:11434").rstrip("/")
        if endpoint.endswith("/api/chat"):
            return endpoint
        if endpoint.endswith("/v1"):
            endpoint = endpoint[:-3].rstrip("/")
        return f"{endpoint}/api/chat"

    def _create_ollama_completion(self, api_args: Dict):
        options = {
            "temperature": api_args.get("temperature", self.temperature),
            "top_p": api_args.get("top_p", self.top_p),
            "num_predict": api_args.get("max_tokens", self.max_tokens),
        }
        extra_body = api_args.get("extra_body", {})
        if extra_body.get("num_ctx", 0) > 0:
            options["num_ctx"] = extra_body["num_ctx"]

        payload = {
            "model": api_args["model"],
            "messages": api_args["messages"],
            "stream": False,
            "options": options,
            "think": bool(extra_body.get("think", False)),
        }
        if api_args.get("response_format"):
            payload["format"] = "json"

        response = self.client.post(
            self._ollama_chat_endpoint(),
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        response_data = response.json()
        content = response_data.get("message", {}).get("content", "")
        prompt_tokens = int(response_data.get("prompt_eval_count", 0) or 0)
        output_tokens = int(response_data.get("eval_count", 0) or 0)
        prompt_duration = float(response_data.get("prompt_eval_duration", 0) or 0) / 1_000_000_000
        output_duration = float(response_data.get("eval_duration", 0) or 0) / 1_000_000_000
        total_duration = float(response_data.get("total_duration", 0) or 0) / 1_000_000_000
        load_duration = float(response_data.get("load_duration", 0) or 0) / 1_000_000_000
        prompt_rate = prompt_tokens / prompt_duration if prompt_duration > 0 else 0.0
        output_rate = output_tokens / output_duration if output_duration > 0 else 0.0
        self.logger.info(
            "Ollama speed model=%s | total=%.3fs load=%.3fs | prompt=%d tokens at %.2f tkn/s | output=%d tokens at %.2f tkn/s"
            % (
                api_args["model"],
                total_duration,
                load_duration,
                prompt_tokens,
                prompt_rate,
                output_tokens,
                output_rate,
            )
        )
        total_tokens = prompt_tokens + output_tokens
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(total_tokens=total_tokens),
        )

    def _respect_delay(self):
        current_time = time.time()
        rpm = self.max_rpm
        delay = self.global_delay
        if rpm > 0:
            if current_time - self.minute_start_time >= 60:
                self.request_count_minute = 0
                self.minute_start_time = current_time
            if self.request_count_minute >= rpm:
                wait_time = 60.1 - (current_time - self.minute_start_time)
                if wait_time > 0:
                    self.logger.warning(
                        f"Global RPM limit ({rpm}) reached. Waiting {wait_time:.2f} seconds."
                    )
                    time.sleep(wait_time)
                self.request_count_minute = 0
                self.minute_start_time = time.time()

        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < delay:
            sleep_time = delay - time_since_last_request
            if hasattr(self, "debug_mode") and self.debug_mode:
                self.logger.debug(f"Global delay: Waiting {sleep_time:.3f} seconds.")
            time.sleep(sleep_time)

        self.last_request_time = time.time()
        self.request_count_minute += 1

    def _respect_key_limit(self, key: str) -> bool:
        rpm = self.max_rpm
        if rpm <= 0:
            return True
        now = time.time()
        count, start_time = self.key_usage.get(key, (0, now))
        if now - start_time >= 60:
            count, start_time = 0, now
            self.key_usage[key] = (count, start_time)
        if count >= rpm:
            wait_time = 60.1 - (now - start_time)
            if wait_time > 0:
                self.logger.warning(
                    f"RPM limit ({rpm}) reached for key {key[:6]}... Waiting {wait_time:.2f} seconds."
                )
                time.sleep(wait_time)
            self.key_usage[key] = (0, time.time())
            return False
        return True

    def _select_api_key(self) -> Optional[str]:
        api_keys = self.multiple_keys_list
        single_key = self.apikey
        if not api_keys and not single_key:
            self.logger.error("No API keys provided in parameters.")
            return None

        if not api_keys:
            if self._respect_key_limit(single_key):
                now = time.time()
                count, start_time = self.key_usage.get(single_key, (0, now))
                if now - start_time >= 60:
                    count = 0
                    start_time = now
                self.key_usage[single_key] = (count + 1, start_time)
                return single_key
            return None

        start_index = self.current_key_index
        for i in range(len(api_keys)):
            index = (start_index + i) % len(api_keys)
            key = api_keys[index]
            if self._respect_key_limit(key):
                now = time.time()
                count, start_time = self.key_usage.get(key, (0, now))
                self.key_usage[key] = (count + 1, start_time)
                self.current_key_index = (index + 1) % len(api_keys)
                return key
        self.logger.error("All available API keys are currently rate-limited.")
        return None

    def _request_translation(
        self,
        prompt: str,
        is_reflection: bool = False,
        purpose: Optional[str] = None,
        expected_count: Optional[int] = None,
        expected_ids: Optional[List[int]] = None,
        max_tokens_override: Optional[int] = None,
    ) -> Optional[TranslationResponse]:
        current_api_key = self._select_api_key()

        if not current_api_key:
            if self.provider in ["LLM Studio", "Ollama"]:
                current_api_key = "dummy-key"
            else:
                raise ConnectionError("No available API key found.")

        if self.provider == "LLM Studio" and not self.endpoint:
            raise ValueError(
                "Endpoint must be specified when using the LLM Studio provider (e.g., http://localhost:1234/v1)."
            )

        if not self._initialize_client(current_api_key):
            raise ConnectionError("Failed to initialize API client.")

        self._respect_delay()

        model_name = self.override_model or self.model
        if ": " in model_name:
            model_name = model_name.split(": ", 1)[1]

        messages = [
            {"role": "system", "content": self._system_prompt_with_reasoning_policy()},
            {"role": "user", "content": prompt},
        ]

        response_max_tokens = int(max_tokens_override or self.max_tokens)
        if (
            self.provider == "Ollama"
            and purpose in {"normal_refinement", "strict_refinement_retry"}
            and response_max_tokens > 8192
        ):
            self.logger.warning(
                f"Ollama {purpose} max tokens {response_max_tokens} is high; clamping to 8192 for JSON stability."
            )
            response_max_tokens = 8192

        api_args = {
            "model": model_name,
            "messages": messages,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": response_max_tokens,
        }

        if self.json_mode_enabled and self.provider == "LLM Studio":
            self.logger.debug("Using 'json_schema' mode for LLM Studio.")
            api_args["response_format"] = {
                "type": "json_schema",
                "json_schema": {"schema": TranslationResponse.model_json_schema()},
            }
        elif self.json_mode_enabled and self.provider in ["OpenAI", "Grok", "Google", "OpenRouter", "Ollama"]:
            self.logger.debug(f"Using 'json_object' mode for {self.provider}.")
            api_args["response_format"] = {"type": "json_object"}

        if self.provider == "OpenAI":
            api_args["frequency_penalty"] = self.frequency_penalty
            api_args["presence_penalty"] = self.presence_penalty
            if self.reasoning_enabled:
                api_args["reasoning_effort"] = self.reasoning_level

        extra_body = self._build_reasoning_extra_body()
        if extra_body:
            api_args["extra_body"] = extra_body

        json_mode = api_args.get("response_format", {}).get("type", "none")
        request_purpose = purpose or ("reflection" if is_reflection else "translation")
        self.logger.info(
            "LLM request purpose=%s provider=%s model=%s json_mode=%s reasoning=%s "
            "think=%s num_ctx=%s max_tokens=%s expected_count=%s expected_ids=%s prompt_length=%s"
            % (
                request_purpose,
                self.provider,
                model_name,
                json_mode,
                self.reasoning_enabled,
                extra_body.get("think") if isinstance(extra_body, dict) else None,
                extra_body.get("num_ctx") if isinstance(extra_body, dict) else None,
                response_max_tokens,
                expected_count,
                expected_ids,
                len(prompt),
            )
        )

        try:
            completion = self._create_completion(api_args)
        except Exception as e:
            self.logger.error(f"API request failed: {e}")
            raise

        if (
            completion.choices
            and completion.choices[0].message
            and completion.choices[0].message.content
        ):
            raw_content = completion.choices[0].message.content
            json_to_parse = self._strip_reasoning_markup(raw_content)

            match = re.search(
                r"```(?:json)?\s*([\[{].*?[\]}])\s*```", json_to_parse, re.DOTALL
            )
            if match:
                self.logger.debug(
                    "Markdown code block detected. Extracting JSON content."
                )
                json_to_parse = match.group(1)
            else:
                start = json_to_parse.find("{")
                end = json_to_parse.rfind("}")
                if start != -1 and end != -1 and end > start:
                    json_to_parse = json_to_parse[start : end + 1]
                else:
                    start = json_to_parse.find("[")
                    end = json_to_parse.rfind("]")
                    if start != -1 and end != -1 and end > start:
                        json_to_parse = json_to_parse[start : end + 1]
            try:
                data_to_validate = json.loads(json_to_parse)
                self.logger.debug(f"Raw JSON content from API: {raw_content}")
                data_to_validate = self._normalize_translation_response_data(
                    data_to_validate,
                    self.logger,
                )
                self.logger.debug(f"Normalized JSON content from API: {data_to_validate}")
                validated_response = TranslationResponse.model_validate(
                    data_to_validate
                )
            except (ValidationError, json.JSONDecodeError) as e:
                self.logger.warning(
                    f"Initial Pydantic validation failed: {e}. Attempting to fix simple dictionary or list format."
                )
                try:
                    simple_data = json.loads(json_to_parse)
                    fixed_translations = []

                    if isinstance(simple_data, dict) and all(
                        k.isdigit() for k in simple_data.keys()
                    ):
                        fixed_translations = [
                            {"id": int(k), "translation": v}
                            for k, v in simple_data.items()
                        ]
                    elif isinstance(simple_data, list):
                        fixed_translations = simple_data

                    if fixed_translations:
                        fixed_data = {"translations": fixed_translations}
                        self.logger.debug(
                            f"Transformed simple response to: {fixed_data}"
                        )
                        validated_response = TranslationResponse.model_validate(
                            fixed_data
                        )
                        self.logger.info(
                            "Successfully parsed response after fixing simple format."
                        )
                    else:
                        raise e
                except (ValidationError, json.JSONDecodeError, Exception) as final_e:
                    self.logger.error(
                        f"Pydantic validation or JSON parsing failed even after attempting fix: {final_e}"
                    )
                    self.logger.debug(f"Raw JSON content from API: {raw_content}")
                    raise
        else:
            self.logger.warning("No valid message content in API response.")
            return None

        self._record_usage(completion)

        if self.reflection_enabled and not is_reflection:
            reflection_prompt = self._build_reflection_prompt(prompt, validated_response)
            try:
                reflected_response = self._request_translation(
                    reflection_prompt,
                    is_reflection=True,
                    purpose="reflection",
                    expected_count=len(validated_response.translations),
                    expected_ids=[item.id for item in validated_response.translations],
                )
                if reflected_response and reflected_response.translations:
                    self.logger.info(
                        "Reflection pass completed and returned revised translations."
                    )
                    return reflected_response
            except Exception as e:
                self.logger.warning(
                    f"Reflection pass failed; using initial translation. {type(e).__name__}: {e}"
                )

        return validated_response

    def _translate(self, src_list: List[str]) -> List[str]:
        if not src_list:
            return []

        RETRYABLE_EXCEPTIONS = (
            openai.RateLimitError,
            openai.APIConnectionError,
            openai.APITimeoutError,
            openai.InternalServerError,
            openai.APIStatusError,
            httpx.RequestError,
        )

        translations = []
        to_lang = self.lang_map.get(self.lang_target, self.lang_target)

        for prompt, num_src in self._assemble_prompts(src_list, to_lang=to_lang):
            api_retry_attempt = 0
            mismatch_retry_attempt = 0

            while True:
                try:
                    parsed_response = self._clean_translation_response(self._request_translation(prompt))

                    if not parsed_response or not parsed_response.translations:
                        raise ValueError(
                            "Received empty or invalid parsed response from API."
                        )

                    if len(parsed_response.translations) != num_src:
                        raise InvalidNumTranslations(
                            f"Expected {num_src}, got {len(parsed_response.translations)}"
                        )

                    translations_dict = {
                        item.id: item.translation
                        for item in parsed_response.translations
                    }
                    ordered_translations = [
                        translations_dict.get(i, "") for i in range(1, num_src + 1)
                    ]
                    batch_sources = src_list[
                        len(translations) : len(translations) + num_src
                    ]
                    self._update_glossary_from_batch(
                        batch_sources, ordered_translations, to_lang
                    )
                    ordered_translations = self._refine_translations_with_glossary(
                        batch_sources, ordered_translations, to_lang
                    )

                    translations.extend(ordered_translations)
                    self.logger.info(
                        f"Successfully translated batch of {num_src}. Tokens used: {self.token_count_last}"
                    )
                    break

                except InvalidNumTranslations as e:
                    mismatch_retry_attempt += 1
                    self.logger.warning(
                        f"Translation structure mismatch: {e}. Attempt {mismatch_retry_attempt}/{self.invalid_repeat_count}."
                    )
                    if mismatch_retry_attempt >= self.invalid_repeat_count:
                        self.logger.error(
                            "Fatal Error: Failed to get correct translation structure after retries."
                        )
                        translations.extend(["[ERROR: Structure Mismatch]"] * num_src)
                        break
                    time.sleep(self.retry_timeout / 2)

                except RETRYABLE_EXCEPTIONS as e:
                    api_retry_attempt += 1
                    self.logger.warning(
                        f"API Error (retryable): {type(e).__name__} - {e}. Attempt {api_retry_attempt}/{self.retry_attempts}."
                    )
                    if api_retry_attempt >= self.retry_attempts:
                        self.logger.error(
                            f"Fatal Error: Failed to connect to API after {self.retry_attempts} attempts."
                        )
                        translations.extend([f"[ERROR: API Failed]"] * num_src)
                        break
                    time.sleep(self.retry_timeout)

                except (
                    ValidationError,
                    json.JSONDecodeError,
                    openai.BadRequestError,
                    openai.AuthenticationError,
                    ValueError,
                ) as e:
                    self.logger.error(
                        f"Fatal Error: An unrecoverable error occurred: {type(e).__name__} - {e}"
                    )
                    self.logger.debug(traceback.format_exc())
                    translations.extend([f"[ERROR: {type(e).__name__}]"] * num_src)
                    break

        return translations

    def updateParam(self, param_key: str, param_content):
        super().updateParam(param_key, param_content)

        if param_key in ["proxy", "multiple_keys", "apikey", "provider", "endpoint"]:
            self.client = None

