import urllib.request
from ordered_set import OrderedSet
from typing import Dict, List, Union, Set, Callable
import time, requests, re, uuid, base64, hmac, functools, json, copy
from collections import OrderedDict

from .exceptions import InvalidSourceOrTargetLanguage, TranslatorSetupFailure, MissingTranslatorParams, TranslatorNotValid
from ballontranslator.utils.textblock import TextBlock
from ..base import BaseModule, DEVICE_SELECTOR
from ballontranslator.utils.registry import Registry
from ballontranslator.utils.io_utils import text_is_empty
from ballontranslator.utils.logger import logger as LOGGER


TRANSLATORS = Registry('translators')
register_translator = TRANSLATORS.register_module

PROXY = urllib.request.getproxies()

LANGMAP_GLOBAL = {
    'Auto': '',
    '简体中文': '',
    '繁體中文': '',
    '日本語': '',
    'English': '',
    '한국어': '',
    'Tiếng Việt': '',
    'čeština': '',
    'Nederlands': '',
    'Français': '',
    'Deutsch': '',
    'magyar nyelv': '',
    'Italiano': '',
    'Polski': '',
    'Português': '',
    'Brazilian Portuguese': '',
    'limba română': '',
    'русский язык': '',
    'Español': '',
    'Türk dili': '',
    'украї́нська мо́ва': '',  
    'Thai': '',
    'Arabic': '',
    'Hindi': '',
    'Malayalam': '',
    'Tamil': '',
}

LANGUAGE_ENGLISH_NAMES = {
    'Auto': 'auto detect',
    '\u7b80\u4f53\u4e2d\u6587': 'Simplified Chinese',
    '\u7e41\u9ad4\u4e2d\u6587': 'Traditional Chinese',
    '\u65e5\u672c\u8a9e': 'Japanese',
    'English': 'English',
    '\ud55c\uad6d\uc5b4': 'Korean',
    'Ti\u1ebfng Vi\u1ec7t': 'Vietnamese',
    '\u010de\u0161tina': 'Czech',
    'Nederlands': 'Dutch',
    'Fran\u00e7ais': 'French',
    'Deutsch': 'German',
    'magyar nyelv': 'Hungarian',
    'Italiano': 'Italian',
    'Polski': 'Polish',
    'Portugu\u00eas': 'Portuguese',
    'limba rom\u00e2n\u0103': 'Romanian',
    '\u0440\u0443\u0441\u0441\u043a\u0438\u0439 \u044f\u0437\u044b\u043a': 'Russian',
    'Espa\u00f1ol': 'Spanish',
    'T\u00fcrk dili': 'Turkish',
    '\u0443\u043a\u0440\u0430\u0457\u0301\u043d\u0441\u044c\u043a\u0430 \u043c\u043e\u0301\u0432\u0430': 'Ukrainian',
    'Thai': 'Thai',
    'Arabic': 'Arabic',
    'Hindi': 'Hindi',
    'Malayalam': 'Malayalam',
    'Tamil': 'Tamil',
}


def lang_display_label(lang: str) -> str:
    english_name = LANGUAGE_ENGLISH_NAMES.get(lang)
    if not english_name or english_name.lower() == str(lang).lower():
        return lang
    return f'{lang} ({english_name})'


def lang_display_to_key(display_lang: str) -> str:
    for lang in LANGUAGE_ENGLISH_NAMES:
        if display_lang == lang_display_label(lang):
            return lang
    return display_lang


SYSTEM_LANG = ''
SYSTEM_LANGMAP = {
    'zh-CN': '简体中文'        
}


def check_language_support(check_type: str = 'source'):
    
    def decorator(set_lang_method):
        @functools.wraps(set_lang_method)
        def wrapper(self, lang: str = ''):
            if check_type == 'source':
                supported_lang_list = self.supported_src_list
            else:
                supported_lang_list = self.supported_tgt_list
            if not lang in supported_lang_list:
                msg = '\n'.join(supported_lang_list)
                raise InvalidSourceOrTargetLanguage(f'Invalid {check_type}: {lang}\n', message=msg)
            return set_lang_method(self, lang)
        return wrapper

    return decorator


class BaseTranslator(BaseModule):

    concate_text = True
    cht_require_convert = False
    translate_by_textblock = False

    _postprocess_hooks = OrderedDict()
    _preprocess_hooks = OrderedDict()
    
    def __init__(self,
                 lang_source: str, 
                 lang_target: str,
                 raise_unsupported_lang: bool = True,
                 **params) -> None:
        super().__init__(**params)
        self.name = ''
        for key in TRANSLATORS.module_dict:
            if TRANSLATORS.module_dict[key] == self.__class__:
                self.name = key
                break
        self.textblk_break = '\n##\n'
        self.lang_source: str = lang_source
        self.lang_target: str = lang_target
        self.lang_map: Dict = LANGMAP_GLOBAL.copy()
        
        try:
            self.setup_translator()
        except Exception as e:
            if isinstance(e, MissingTranslatorParams):
                raise e
            else:
                raise TranslatorSetupFailure(e)
            
        # enable traditional chinese by converting from simplified chinese
        if self.cht_require_convert and not self.lang_map['繁體中文']:
            self.lang_map['繁體中文'] = self.lang_map['简体中文']

        self.valid_lang_list = [lang for lang in self.lang_map if self.lang_map[lang] != '']

        try:
            self.set_source(lang_source)
            self.set_target(lang_target)
        except InvalidSourceOrTargetLanguage as e:
            if raise_unsupported_lang:
                raise e
            else:
                lang_source = self.supported_src_list[0]
                lang_target = self.supported_tgt_list[0]
                self.set_source(lang_source)
                self.set_target(lang_target)

    def _setup_translator(self):
        raise NotImplementedError

    def setup_translator(self):
        self._setup_translator()

    @check_language_support(check_type='source')
    def set_source(self, lang: str):
        self.lang_source = lang

    @check_language_support(check_type='target')
    def set_target(self, lang: str):
        self.lang_target = lang

    def _translate(self, src_list: List[str]) -> List[str]:
        raise NotImplementedError

    def translate(self, text: Union[str, List]) -> Union[str, List]:
        if text_is_empty(text):
            return text
        if not self.all_model_loaded():
            self.load_model()

        is_list = isinstance(text, List)
        concate_text = is_list and self.concate_text and not self.translate_by_textblock
        text_source = self.textlist2text(text) if concate_text else text
        
        src_is_list = isinstance(text_source, List)
        if src_is_list: 
            text_trans = self._translate(text_source)
        else:
            text_trans = self._translate([text_source])[0]
        
        if text_trans is None:
            if is_list:
                text_trans = [''] * len(text)
            else:
                text_trans = ''
        elif concate_text:
            text_trans = self.text2textlist(text_trans)
            
        if is_list:
            try:
                assert len(text_trans) == len(text)
            except:
                LOGGER.error('This translator seems to messed up the translation which resulted in inconsistent translated line count.\n \
                             Set concate_text to False or change textblk_break in the source code may solve the problem.')
                raise

        return text_trans

    def textlist2text(self, text_list: List[str]) -> str:
        # some translators automatically strip '\n'
        # so we insert '\n###\n' between concated text instead of '\n' to avoid mismatch
        return self.textblk_break.join(text_list)

    def text2textlist(self, text: str) -> List[str]:
        breaker = self.textblk_break.replace('\n', '') or '\n'
        text_list = text.split(breaker)
        return [text.lstrip().rstrip() for text in text_list]

    def provider_result_label(self) -> str:
        if self.name == 'google':
            return 'Google'
        if self.name == 'DeepL':
            return 'DeepL'
        return ''

    def _store_provider_results(
        self,
        textblk_lst: List[TextBlock],
        non_empty_ids: List[int],
        translations: List[str],
        label: str = '',
    ):
        label = label or self.provider_result_label()
        if not label:
            return
        for ii, idx in enumerate(non_empty_ids):
            if ii >= len(translations):
                break
            results = getattr(textblk_lst[idx], 'translation_provider_results', None)
            if not isinstance(results, dict):
                results = {}
            results[label] = translations[ii] or ''
            textblk_lst[idx].translation_provider_results = results
            if label in ('Google', 'DeepL', 'DeepL Free'):
                textblk_lst[idx].translation_draft = translations[ii] or ''

    def translate_textblk_lst(self, textblk_lst: List[TextBlock]):
        '''
        only textblks with non-empty source text would be passed to translator
        '''
        non_empty_ids = []
        text_list = []
        translations = []
        for ii, blk in enumerate(textblk_lst):
            text = blk.get_text()
            if text.strip() != '':
                non_empty_ids.append(ii)
                text_list.append(text)
            translations.append(text)

        # non_empty_txtlst_str = ',\n'.join(text_list)
        # LOGGER.debug(f'non empty src text list: \n[{non_empty_txtlst_str}]')

        for callback_name, callback in self._preprocess_hooks.items():
            callback(translations = translations, textblocks = textblk_lst, translator = self, source_text = text_list)

        if len(text_list) > 0:
            _translations = self.translate(text_list)
            self._store_provider_results(textblk_lst, non_empty_ids, _translations)
            for ii, idx in enumerate(non_empty_ids):
                translations[idx] = _translations[ii]

        for callback_name, callback in self._postprocess_hooks.items():
            callback(translations = translations, textblocks = textblk_lst, translator = self)

        for tr, blk in zip(translations, textblk_lst):
            blk.translation = tr

    def review_translations(self, src_list: List[str], draft_list: List[str]) -> List[str]:
        raise NotImplementedError(f'{self.name} does not support LLM translation review.')

    def supports_translation_review(self) -> bool:
        return type(self).review_translations is not BaseTranslator.review_translations

    def review_address_translations(self, src_list: List[str], draft_list: List[str]) -> List[str]:
        raise NotImplementedError(f'{self.name} does not support LLM address/pronoun review.')

    def supports_address_review(self) -> bool:
        return type(self).review_address_translations is not BaseTranslator.review_address_translations

    def review_uncensored_translations(self, src_list: List[str], draft_list: List[str]) -> List[str]:
        raise NotImplementedError(f'{self.name} does not support uncensored LLM translation review.')

    def supports_uncensored_review(self) -> bool:
        return type(self).review_uncensored_translations is not BaseTranslator.review_uncensored_translations

    def rewrite_and_shorten_translations(self, src_list: List[str], draft_list: List[str]) -> List[str]:
        raise NotImplementedError(f'{self.name} does not support LLM speech-bubble shortening.')

    def supports_translation_shortening(self) -> bool:
        return type(self).rewrite_and_shorten_translations is not BaseTranslator.rewrite_and_shorten_translations

    def review_textblk_lst(self, textblk_lst: List[TextBlock]):
        '''
        Review existing translations without rerunning OCR, inpainting, or first-step translation.
        '''
        self._revise_textblk_lst(textblk_lst, self.review_translations)

    def review_address_textblk_lst(self, textblk_lst: List[TextBlock]):
        '''
        Review selected translations for speaker/addressee, pronouns, and direct address.
        '''
        self._revise_textblk_lst(textblk_lst, self.review_address_translations)

    def review_uncensored_textblk_lst(self, textblk_lst: List[TextBlock]):
        '''
        Review selected translations for omissions, sanitization, and censorship.
        '''
        self._revise_textblk_lst(textblk_lst, self.review_uncensored_translations)

    def rewrite_and_shorten_textblk_lst(self, textblk_lst: List[TextBlock]):
        '''
        Rewrite existing translations into shorter speech-bubble text without rerunning OCR or inpainting.
        '''
        self._revise_textblk_lst(textblk_lst, self.rewrite_and_shorten_translations)

    def _revise_textblk_lst(self, textblk_lst: List[TextBlock], revise):
        non_empty_ids = []
        text_list = []
        draft_list = []
        reviewed = [blk.translation for blk in textblk_lst]

        for ii, blk in enumerate(textblk_lst):
            source = blk.get_text()
            if source.strip() != '':
                non_empty_ids.append(ii)
                text_list.append(source)
                draft_list.append(blk.translation or source)

        if len(text_list) > 0:
            _translations = revise(text_list, draft_list)
            if _translations is None:
                _translations = []
            if len(_translations) < len(non_empty_ids):
                _translations = list(_translations) + draft_list[len(_translations):]
            for ii, idx in enumerate(non_empty_ids):
                reviewed[idx] = _translations[ii]
                textblk_lst[idx].translation_llm_review = _translations[ii]

        for callback_name, callback in self._postprocess_hooks.items():
            callback(translations=reviewed, textblocks=textblk_lst, translator=self)

        for tr, blk in zip(reviewed, textblk_lst):
            blk.translation = tr

    def supported_languages(self) -> List[str]:
        return self.valid_lang_list

    @property
    def supported_tgt_list(self) -> List[str]:
        return self.valid_lang_list

    @property
    def supported_src_list(self) -> List[str]:
        return self.valid_lang_list
        
    def delay(self) -> float:
        if 'delay' in self.params:
            delay = self.params['delay']
            if delay:
                try:
                    return float(delay)
                except:
                    pass
        return 0.

@register_translator('Copy Source')
class TransSource(BaseTranslator):

    concate_text = False
    cht_require_convert = True
    params: Dict = {
        'description': 'Return source text as translation'
    }

    def _setup_translator(self):
        for k in self.lang_map.keys():
            self.lang_map[k] = 'dummy language'
        self.register_preprocess_hooks
        
    def _translate(self, src_list: List[str]) -> List[str]:
        return copy.copy(src_list)
