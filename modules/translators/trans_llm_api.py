import re
import time
import json
import traceback
from typing import Any, List, Dict, Optional, Type

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
        description="Enabled category key such as name, place, organization, title, term, honorific, or catchphrase.",
    )
    note: str = Field(default="", description="Short optional usage note.")


class GlossaryResponse(BaseModel):
    entries: List[GlossaryEntry] = Field(
        default_factory=list,
        description="Reusable glossary entries extracted from translated text.",
    )


AUTO_GLOSSARY_CATEGORY_CONFIG = {
    "name": {
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
            "description": "Select the LLM provider.",
        },
        "apikey": {
            "value": "",
            "description": "Single API key to use if multiple keys are not provided.",
        },
        "multiple_keys": {
            "type": "editor",
            "value": "",
            "description": "API keys separated by semicolons (;). Requests will rotate through these keys.",
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
            "description": "Base URL for the API. Leave empty for provider default.",
        },
        "system_prompt": {
            "type": "editor",
            "value": 'You are an expert translator. Your task is to accurately translate the given text snippets. You MUST provide the output strictly in the specified JSON format, without any additional explanations or markdown formatting. Return only valid JSON in this exact shape: {"translations":[{"id":1,"translation":"Translated text here."}]}. The JSON object must have a single key \'translations\', which is a list of objects, each with an \'id\' (integer) and a \'translation\' (string).\n\nExample Output Schema:\n{"translations": [{"id": 1, "translation": "Translated text here."}]}',
            "description": "System message to instruct the LLM on its role and required output format.",
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
            "description": "Global delay in seconds between requests.",
        },
        "max tokens": {
            "value": 4096,
            "description": "Maximum tokens for the response. Very high values can slow down local models and make JSON output less stable.",
        },
        "reasoning": {
            "type": "checkbox",
            "value": False,
            "description": "For local translation models, disabling reasoning is usually faster and more stable for JSON output.",
        },
        "reasoning level": {
            "type": "selector",
            "options": ["low", "medium", "high"],
            "value": "medium",
            "description": "Reasoning effort used when reasoning is enabled.",
        },
        "reflection": {
            "type": "checkbox",
            "value": False,
            "description": "Run an additional LLM review pass after translation. This adds extra LLM calls.",
        },
        "reflection prompt": {
            "type": "editor",
            "value": "Review the draft translation against the original source text. Check meaning, terminology, tone, fluency, punctuation, and whether the number of translated items matches the input. Revise only where the translation can be improved. Return only the final improved JSON object in the required schema.",
            "description": "Instructions used for the optional reflection/revision API call.",
        },
        "previous context pages": {
            "value": 0,
            "description": "Number of previous project pages to include as source and existing translation context for LLM translation. 0 disables previous-page context.",
        },
        "include next context page": {
            "type": "checkbox",
            "value": False,
            "description": "Also include the next project page as context when its text is available. This helps foreshadow names and references but increases token usage.",
        },
        "document context pages": {
            "value": 0,
            "description": "Include up to this many pages from the project as document context for each LLM batch. 0 disables document-level context; higher values cost more tokens.",
        },
        "context max characters": {
            "value": 6000,
            "description": "Maximum characters allowed for all LLM context sections combined before truncation. Lower this if the model context window is small.",
        },
        "use glossary": {
            "type": "checkbox",
            "value": True,
            "description": "Include the glossary in translation prompts so character names, places, organizations, titles, and recurring terms stay consistent.",
        },
        "auto build glossary": {
            "type": "checkbox",
            "value": True,
            "description": "After each LLM translation batch, ask the model to extract reusable glossary entries from the source/translation pairs. This improves consistency but adds extra API calls.",
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
            "description": "Extract or refine glossary entries with the LLM. This adds extra LLM calls.",
        },
        "glossary max entries": {
            "value": 200,
            "description": "Maximum number of glossary entries kept in the translator settings. Higher values preserve more terms but increase prompt size and cost.",
        },
        "glossary prompt": {
            "type": "editor",
            "value": "Use glossary entries as terminology guidance only. Apply preferred target terms naturally in the target language. Never include category labels, notes, comments, or bracketed metadata such as [CHARACTER], [PLACE], [ORGANIZATION], [TITLE], or [TERM] in the translation output.",
            "description": "Custom instructions inserted before glossary entries in translation and glossary refinement prompts.",
        },
        "glossary": {
            "type": "editor",
            "value": "",
            "description": "Persistent glossary used by the translator. Format: source => target [category] # optional note. You can edit it manually; auto build glossary appends or updates entries.",
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
            'description': 'check it if you\'re running it locally on a single device and encountered a crash due to vram OOM',
            'type': 'checkbox',
        }
    }

    def _setup_translator(self):
        self.lang_map = {
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
        self.context_project = None
        self.context_page_key = ""

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
                endpoint = "http://localhost:11434/v1"

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
    def reflection_enabled(self) -> bool:
        return bool(self.get_param_value("reflection"))

    @property
    def reflection_prompt(self) -> str:
        return self.get_param_value("reflection prompt")

    @property
    def use_glossary_enabled(self) -> bool:
        return bool(self.get_param_value("use glossary"))

    @property
    def auto_build_glossary_enabled(self) -> bool:
        return bool(self.get_param_value("auto build glossary"))

    @property
    def glossary_refinement_enabled(self) -> bool:
        return bool(self.get_param_value("glossary refinement pass"))

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
        project_glossary = getattr(self, "project_glossary_text", "")
        if project_glossary.strip():
            return project_glossary
        return self.get_param_value("glossary") or ""

    @property
    def glossary_prompt(self) -> str:
        project_prompt = getattr(self, "project_glossary_prompt", "")
        if project_prompt.strip():
            return project_prompt.strip()
        return self.get_param_value("glossary prompt") or ""

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

        prompt = (
            f"Please translate the following text snippets from {from_lang} to {to_lang}. "
            f"The input is provided as a JSON array. Respond with a JSON object in the specified format.\n\n"
            f"{context_section}"
            f"{glossary_section}"
            f"INPUT:\n{input_json_str}"
        )

        yield prompt, len(queries)

    def _glossary_prompt_section(self) -> str:
        if not self.use_glossary_enabled:
            return ""
        glossary = self.glossary_text.strip()
        if not glossary:
            return ""
        prompt = self.glossary_prompt.strip()
        return (
            "GLOSSARY:\n"
            f"{prompt}\n"
            f"{glossary}\n\n"
        )

    def set_project_glossary(self, glossary):
        if isinstance(glossary, dict):
            self.project_glossary_text = glossary.get("entries", "") or ""
            self.project_glossary_prompt = glossary.get("prompt", "") or ""
        elif isinstance(glossary, str):
            self.project_glossary_text = glossary
            self.project_glossary_prompt = ""
        else:
            self.project_glossary_text = ""
            self.project_glossary_prompt = ""

    def get_project_glossary(self) -> Dict[str, str]:
        return {
            "entries": self.glossary_text,
            "prompt": self.glossary_prompt,
        }

    def _system_prompt_with_reasoning_policy(self) -> str:
        prompt = self.system_prompt
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
        if provider == "Ollama":
            return {"think": bool(self.reasoning_enabled)}
        if not self.reasoning_enabled:
            return {}
        if provider == "OpenRouter":
            return {"reasoning": {"effort": level}}
        if provider == "LLM Studio":
            return {"reasoning": {"effort": level}, "think": True}
        if provider in ["Google", "Grok"]:
            return {"reasoning_effort": level}
        return {}

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
        if isinstance(data, dict) and not data:
            if logger is not None:
                logger.warning("LLM returned empty glossary JSON object; no glossary entries were extracted.")
            return {"entries": []}

        if isinstance(data, list):
            return {"entries": data}

        if not isinstance(data, dict):
            return data

        if "entries" in data:
            entries = data.get("entries")
            if entries is None:
                entries = []
            elif isinstance(entries, dict):
                entries = [entries]
            normalized = dict(data)
            normalized["entries"] = entries
            return normalized

        for key in ("glossary", "terms", "items"):
            entries = data.get(key)
            if isinstance(entries, list):
                return {"entries": entries}

        if "source" in data and "target" in data:
            return {"entries": [data]}

        return data

    def _build_reflection_prompt(
        self, original_prompt: str, draft_response: TranslationResponse
    ) -> str:
        draft_json = draft_response.model_dump_json(indent=2)
        return (
            f"{self.reflection_prompt}\n\n"
            "ORIGINAL TRANSLATION TASK:\n"
            f"{original_prompt}\n\n"
            "DRAFT TRANSLATION JSON:\n"
            f"{draft_json}\n\n"
            "Return the reviewed and improved translation as JSON with the same "
            "'translations' list and the same numeric ids. Required schema: "
            '{"translations":[{"id":1,"translation":"Reviewed translation"}]}.'
        )

    def _canonical_glossary_category(self, category: str) -> str:
        raw_category = (category or "").strip().lower()
        raw_category = raw_category.strip("[](){}")
        raw_category = re.sub(r"\s+", " ", raw_category)
        raw_category = raw_category.removesuffix(" name")
        for canonical, config in AUTO_GLOSSARY_CATEGORY_CONFIG.items():
            if raw_category in config["aliases"]:
                return canonical
        return raw_category or "term"

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

    def _format_glossary_entry(
        self, entry: GlossaryEntry, category: Optional[str] = None
    ) -> str:
        category = category or self._canonical_glossary_category(entry.category)
        note = (entry.note or "").strip()
        line = f"{entry.source.strip()} => {entry.target.strip()} [{category}]"
        if note:
            line = f"{line} # {note}"
        return line

    def _parse_glossary_lines(self) -> Dict[str, str]:
        entries = {}
        for line in self.glossary_text.splitlines():
            clean = line.strip()
            if not clean or clean.startswith("#") or "=>" not in clean:
                continue
            source = clean.split("=>", 1)[0].strip()
            if source:
                entries[source] = clean
        return entries

    def _save_glossary_entries(self, entries: List[GlossaryEntry]) -> int:
        if not entries or self.glossary_max_entries == 0:
            return 0

        enabled_categories = self._enabled_auto_glossary_categories()
        if not enabled_categories:
            return 0

        saved_count = 0
        glossary_lines = self._parse_glossary_lines()
        for entry in entries:
            source = entry.source.strip()
            target = entry.target.strip()
            category = self._canonical_glossary_category(entry.category)
            if not source or not target:
                continue
            if category not in enabled_categories:
                continue
            glossary_lines[source] = self._format_glossary_entry(entry, category=category)
            saved_count += 1

        limited_lines = list(glossary_lines.values())[-self.glossary_max_entries :]
        self.set_param_value("glossary", "\n".join(limited_lines), convert_dtype=False)
        self.project_glossary_text = "\n".join(limited_lines)
        return saved_count

    def _build_glossary_extraction_prompt(
        self, src_list: List[str], translations: List[str], to_lang: str
    ) -> str:
        from_lang = self.lang_map.get(self.lang_source, self.lang_source)
        pairs = [
            {"id": i + 1, "source": source, "translation": translation}
            for i, (source, translation) in enumerate(zip(src_list, translations))
        ]
        existing_glossary = self.glossary_text.strip() or "(empty)"
        category_prompt = self._auto_glossary_category_prompt()
        return (
            f"Extract a reusable translation glossary from {from_lang} to {to_lang}.\n"
            f"{category_prompt}\n"
            "Do not add generic words, full sentences, ordinary phrases, one-off "
            "dialogue, or style notes. Metadata belongs only in the glossary entry; "
            "it must never be copied into translated text.\n\n"
            "Return JSON only with the GlossaryResponse schema: "
            '{"entries":[{"source":"term","target":"translated term","category":"term","note":""}]}. '
            "Each entry must contain source, target, category, and optional note. "
            "Category and note are metadata for the glossary only; they must never "
            "be copied into translations.\n\n"
            f"EXISTING GLOSSARY:\n{existing_glossary}\n\n"
            f"TRANSLATION PAIRS:\n{json.dumps(pairs, ensure_ascii=False, indent=2)}"
        )

    def _update_glossary_from_batch(
        self, src_list: List[str], translations: List[str], to_lang: str
    ):
        if not self.auto_build_glossary_enabled or not src_list:
            return
        if not self._enabled_auto_glossary_categories():
            return

        system_prompt = (
            "You extract concise translation glossaries. Return only valid JSON "
            'matching the GlossaryResponse schema: {"entries":[{"source":"term",'
            '"target":"translated term","category":"term","note":""}]}.'
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
        except Exception as e:
            self.logger.warning(
                f"Glossary extraction failed; continuing without glossary update. {type(e).__name__}: {e}"
            )

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
            "Only change text where the glossary improves consistency. Preserve "
            "meaning, tone, line count, ids, and natural target-language grammar. "
            "Do not insert glossary category labels, notes, comments, or bracketed "
            "metadata into the translation text. "
            "Return only JSON in the required translation schema.\n\n"
            f"{self._translation_context_prompt_section()}"
            f"{self._glossary_prompt_section()}"
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

        if self.provider == "LLM Studio":
            api_args["response_format"] = {
                "type": "json_schema",
                "json_schema": {"schema": response_model.model_json_schema()},
            }
        elif self.provider in ["OpenAI", "Grok", "Google", "OpenRouter", "Ollama"]:
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

        if self.provider == "LLM Studio":
            self.logger.debug("Using 'json_schema' mode for LLM Studio.")
            api_args["response_format"] = {
                "type": "json_schema",
                "json_schema": {"schema": TranslationResponse.model_json_schema()},
            }
        elif self.provider in ["OpenAI", "Grok", "Google", "OpenRouter", "Ollama"]:
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

