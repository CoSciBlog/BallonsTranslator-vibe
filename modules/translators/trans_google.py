from .base import *
import requests
import json
import html # For html.unescape


# --- exceptions ---
class ProviderError(Exception):
    pass


class TranslateError(ProviderError):
    pass


USER_AGENT_BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36"
GOOGLE_API_URL = "https://translate.googleapis.com/translate_a/single"


class GoogleTranslateProviderPython:
    """Lightweight client for Google's text translation JSON endpoint."""

    def __init__(self, timeout: int = 10):
        self.base_headers = {
            "User-Agent": USER_AGENT_BROWSER,
        }
        self.fetch_opts = {"timeout": timeout}
        self.requests_session = requests.Session()
        self.requests_session.headers.update(self.base_headers)

    def _request(self, text: str, target_language: str, source_language: str):
        try:
            response = self.requests_session.get(
                GOOGLE_API_URL,
                params={
                    "client": "gtx",
                    "sl": source_language or "auto",
                    "tl": target_language,
                    "dt": "t",
                    "q": text,
                },
                **self.fetch_opts,
            )

            if response.status_code >= 400:
                message = response.reason
                try:
                    error_data = response.json()
                    if "error" in error_data and isinstance(error_data["error"], dict):
                        message = error_data["error"].get("message", response.reason)
                except json.JSONDecodeError:
                    pass  # Using response.reason
                raise ProviderError(f"HTTP {response.status_code}: {message}")

            response_data = response.json()

            if isinstance(response_data, dict) and "error" in response_data:
                error_details = response_data.get("error")
                msg = "API error"
                if isinstance(error_details, dict) and "message" in error_details:
                    msg = error_details["message"]
                raise ProviderError(msg)
            return response_data
        except requests.exceptions.RequestException as e:
            raise ProviderError(f"Request failed: {e}")
        except json.JSONDecodeError:
            raw_text = (
                response.text[:200]
                if response and hasattr(response, "text")
                else "NoResponseObject"
            )
            raise ProviderError(f"Failed to decode JSON. Raw: {raw_text}")

    def translate(
        self, text_list: List[str], target_language: str, source_language: str = "auto"
    ) -> Dict[str, any]:
        """Translate text snippets, optionally auto-detecting the source language."""
        if not text_list:
            return {"lang": target_language, "translations": []}

        translations_result = []
        for text_item in text_list:
            if not text_item or not text_item.strip():
                translations_result.append("")
                continue

            try:
                response_data = self._request(text_item, target_language, source_language)
                translated_segments = response_data[0] if response_data and isinstance(response_data, list) else []
                extracted_text = ''.join(
                    segment[0]
                    for segment in translated_segments
                    if isinstance(segment, list) and segment and isinstance(segment[0], str)
                )

                if extracted_text:
                    translations_result.append(html.unescape(extracted_text))
                else:
                    translations_result.append("")
            except ProviderError:
                translations_result.append("")

        return {"lang": target_language, "translations": translations_result}


@register_translator("google")
class TransGoogle(BaseTranslator):

    concate_text = False
    params: Dict = {
        "delay": 0.0,
        "auto detect source language": {
            "type": "checkbox",
            "value": True,
            "description": "Let Google detect the source language for each text block. Recommended for mixed or Traditional Chinese projects; disable only when forced source-language translation is intentional.",
        },
    }

    def _setup_translator(self):
        self.internal_google_translator = GoogleTranslateProviderPython()

        self.lang_map["Auto"] = "auto"
        self.lang_map["简体中文"] = "zh-CN"
        self.lang_map["繁體中文"] = "zh-TW"
        self.lang_map["日本語"] = "ja"
        self.lang_map["English"] = "en"
        self.lang_map["한국어"] = "ko"
        self.lang_map["Tiếng Việt"] = "vi"
        self.lang_map["čeština"] = "cs"
        self.lang_map["Nederlands"] = "nl"
        self.lang_map["Français"] = "fr"
        self.lang_map["Deutsch"] = "de"
        self.lang_map["magyar nyelv"] = "hu"
        self.lang_map["Italiano"] = "it"
        self.lang_map["Polski"] = "pl"
        self.lang_map["Português"] = "pt"
        self.lang_map["limba română"] = "ro"
        self.lang_map["русский язык"] = "ru"
        self.lang_map["Español"] = "es"
        self.lang_map["Türk dili"] = "tr"
        self.lang_map["украї́нська мо́ва"] = "uk"
        self.lang_map["Thai"] = "th"
        self.lang_map["Arabic"] = "ar"
        self.lang_map["Hindi"] = "hi"
        self.lang_map["Malayalam"] = "ml"
        self.lang_map["Tamil"] = "ta"

    def _translate(self, src_list: List[str]) -> List[str]:
        if not src_list:
            return []

        try:
            source_lang_code = (
                "auto"
                if self.get_param_value("auto detect source language")
                else self.lang_map.get(self.lang_source, "auto")
            )
            target_lang_code = self.lang_map.get(self.lang_target, "en")

            response_data = self.internal_google_translator.translate(
                src_list,
                target_language=target_lang_code,
                source_language=source_lang_code,
            )

            if response_data and isinstance(response_data.get("translations"), list):
                translated_texts = response_data["translations"]
                if len(translated_texts) == len(src_list):
                    return translated_texts

            # In case of mismatch or error, we return empty strings
            return [""] * len(src_list)

        except ProviderError as e:
            LOGGER.error(f"Google Translate provider error: {e}")
            return [""] * len(src_list)
        except Exception as e:
            LOGGER.error(f"An unexpected error occurred in Google Translate: {e}")
            return [""] * len(src_list)
