"""Shared request dispatch for Chat Completions and API/subscription Responses."""

from __future__ import annotations

import os
import re
import threading
import time
import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

from .context.errors import provider_error_message
from .context.token_usage import format_completion_token_usage
from .exceptions import (
    LLMApiKeyRequiredError,
    LLMAuthenticationError,
    LLMOutputLimitError,
    LLMRequestStopped,
    LLMUserActionRequiredError,
)
from .base import unload_models_before_llm_request
from ballontranslator.utils.llm_profiles import (
    LLMProfile,
    PROVIDER_DEFAULTS,
    THINKING_AUTO,
    THINKING_DISABLED,
    normalize_thinking_level,
    ollama_native_chat_url,
    resolve_api_key,
)

if TYPE_CHECKING:
    from .codex import CodexChatSession, CodexTurnState
    from .openai_responses import OpenAIResponsesSession

OPENAI_MAX_TOKENS_MODELS = frozenset({
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4o",
    "gpt-4o-mini",
})
_CHAT_COMPLETIONS_SUFFIX = '/chat/completions'


def _normalized_base_url(url: str) -> str:
    return str(url or '').strip().rstrip('/')


def _openai_sdk_base_url(url: str) -> str:
    """Return the API base expected by the OpenAI SDK chat resource.

    Provider documentation often presents the complete HTTP endpoint, while
    ``client.chat.completions.create`` adds that endpoint path itself.

    >>> _openai_sdk_base_url('https://example.test/v1/chat/completions/')
    'https://example.test/v1'
    >>> _openai_sdk_base_url('https://example.test/v1')
    'https://example.test/v1'
    """
    base_url = str(url or '').strip()
    endpoint_url = base_url.rstrip('/')
    if endpoint_url.endswith(_CHAT_COMPLETIONS_SUFFIX):
        parent_url = endpoint_url[:-len(_CHAT_COMPLETIONS_SUFFIX)]
        if parent_url:
            return parent_url
    return base_url


def _uses_provider_base_url(base_url: str, provider: str) -> bool:
    provider_url = _normalized_base_url(
        PROVIDER_DEFAULTS[provider]['base_url']
    ).lower()
    base_url = _normalized_base_url(base_url).lower()
    return base_url == provider_url or base_url.startswith(
        f'{provider_url}/'
    )


def gpt_model_version(model: str) -> Optional[Tuple[int, int]]:
    """Recognize GPT IDs, including gateway namespaces and model suffixes.

    >>> gpt_model_version('openai/gpt-5.6-luna')
    (5, 6)
    >>> gpt_model_version('gpt-4o-mini')
    (4, 0)
    >>> gpt_model_version('custom-gpt-6') is None
    True
    """
    name = str(model or '').strip().rsplit('/', 1)[-1].lower()
    match = re.match(r'^gpt-(\d+)(?:\.(\d+)|o)?(?:[-:]|$)', name)
    return (int(match[1]), int(match[2] or 0)) if match else None


def openai_chat_completion_args(
    profile: LLMProfile,
    model: str,
) -> Dict[str, Any]:
    """Map provider-neutral profile values to OpenAI chat API arguments.

    Native OpenAI models default to ``max_completion_tokens`` so future model
    names do not need version-pattern guesses. Only explicitly listed older
    models and compatibility endpoints retain ``max_tokens``. GPT-5.5+ models
    omit temperature and top_p regardless of the endpoint, including gateways.

    >>> profile = LLMProfile.from_provider('OpenAI')
    >>> openai_chat_completion_args(profile, 'gpt-5.5')
    {'max_completion_tokens': 8192}
    >>> openai_chat_completion_args(profile, 'gpt-4o')['temperature']
    0.1
    """
    if profile.backend == 'codex':
        return {}
    base_url = _normalized_base_url(_openai_sdk_base_url(profile.base_url))
    openai_base_url = _normalized_base_url(
        PROVIDER_DEFAULTS['OpenAI']['base_url']
    )
    model_name = str(model or '').strip().rsplit('/', 1)[-1].lower()
    is_native_openai = not base_url or base_url == openai_base_url
    args: Dict[str, Any] = {}
    gpt_version = gpt_model_version(model)
    if gpt_version is None or gpt_version < (5, 5):
        args['top_p'] = float(profile.top_p)
        args['temperature'] = float(profile.temperature)
    token_limit_key = (
        'max_completion_tokens'
        if is_native_openai and model_name not in OPENAI_MAX_TOKENS_MODELS
        else 'max_tokens'
    )
    args[token_limit_key] = int(profile.max_tokens)

    thinking_level = normalize_thinking_level(profile.thinking_level)
    if thinking_level == THINKING_AUTO:
        return args
    if thinking_level != THINKING_DISABLED:
        args['reasoning_effort'] = thinking_level
        return args
    if _uses_provider_base_url(base_url, 'DeepSeek'):
        args['extra_body'] = {'thinking': {'type': 'disabled'}}
    elif _uses_provider_base_url(base_url, 'OpenRouter'):
        args['extra_body'] = {'reasoning': {'effort': 'none'}}
    else:
        args['reasoning_effort'] = 'none'
    return args


def openai_json_response_format(
    profile: LLMProfile,
    name: str,
    schema: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the profile-compatible JSON response format.

    >>> profile = LLMProfile.from_provider('LM Studio')
    >>> openai_json_response_format(profile, 'demo', {'type': 'object'})['type']
    'json_schema'
    >>> profile.json_schema_response_format = False
    >>> openai_json_response_format(profile, 'demo', {})
    {'type': 'json_object'}
    """
    if not profile.json_schema_response_format:
        return {'type': 'json_object'}
    return {
        'type': 'json_schema',
        'json_schema': {
            'name': name,
            'strict': True,
            'schema': schema,
        },
    }


def ollama_native_chat_payload(
    api_args: Dict[str, Any],
    context_length: int,
) -> Dict[str, Any]:
    """Translate the app's chat arguments to Ollama's native request shape.

    Native Ollama is used only for an explicit per-profile context length,
    because its OpenAI-compatible endpoint does not provide a stable request
    field for changing ``num_ctx``.

    >>> payload = ollama_native_chat_payload({
    ...     'model': 'demo:7b', 'messages': [{'role': 'user', 'content': 'Hi'}],
    ...     'max_tokens': 128, 'temperature': 0.2,
    ... }, 16384)
    >>> payload['options']
    {'num_ctx': 16384, 'num_predict': 128, 'temperature': 0.2}
    """
    messages = []
    for original in api_args.get('messages', ()):  # OpenAI text/vision parts
        if not isinstance(original, dict):
            continue
        content = original.get('content', '')
        images = []
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get('type') == 'text':
                    text_parts.append(str(part.get('text', '')))
                elif part.get('type') == 'image_url':
                    image = part.get('image_url', '')
                    if isinstance(image, dict):
                        image = image.get('url', '')
                    image = str(image or '')
                    if image.startswith('data:') and ',' in image:
                        image = image.split(',', 1)[1]
                    if image:
                        images.append(image)
            content = '\n'.join(part for part in text_parts if part)
        message = {
            'role': str(original.get('role', 'user')),
            'content': str(content or ''),
        }
        if images:
            message['images'] = images
        messages.append(message)

    options: Dict[str, Any] = {'num_ctx': int(context_length)}
    for source, target in (
        ('max_tokens', 'num_predict'),
        ('max_completion_tokens', 'num_predict'),
        ('temperature', 'temperature'),
        ('top_p', 'top_p'),
        ('frequency_penalty', 'frequency_penalty'),
        ('presence_penalty', 'presence_penalty'),
        ('seed', 'seed'),
        ('stop', 'stop'),
    ):
        if source in api_args:
            options[target] = api_args[source]

    payload: Dict[str, Any] = {
        'model': str(api_args.get('model', '')),
        'messages': messages,
        'stream': False,
        'options': options,
    }
    response_format = api_args.get('response_format')
    if isinstance(response_format, dict):
        format_type = response_format.get('type')
        if format_type == 'json_schema':
            schema = response_format.get('json_schema', {}).get('schema')
            if isinstance(schema, dict):
                payload['format'] = schema
        elif format_type == 'json_object':
            payload['format'] = 'json'
    reasoning = normalize_thinking_level(api_args.get('reasoning_effort'))
    if reasoning == THINKING_DISABLED or str(reasoning).lower() == 'none':
        payload['think'] = False
    elif reasoning != THINKING_AUTO:
        payload['think'] = reasoning
    return payload


@dataclass(frozen=True)
class LLMChatResult:
    content: str
    usage: Any = None
    finish_reason: str = ''
    prompt_cache_diagnostics: object = None
    codex_response_items: Tuple[Dict[str, object], ...] = ()
    codex_cache_key: str = ''
    codex_account_generation: Optional[int] = None


class LLMChatRequestError(RuntimeError):
    """A normalized provider status error from Chat Completions."""

    def __init__(self, provider_error: Exception) -> None:
        self.provider_error = provider_error
        super().__init__(provider_error_message(provider_error))


class LLMChatRequester:
    """Issue one profile-backed API or Codex chat request.

    Prompt construction and retries stay with the owning Translator or OCR
    module; this boundary owns only transport and provider normalization.

    >>> LLMChatRequester().client is None
    True
    """

    dummy_api_key = 'dummy-key'

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.client: Any = None
        self.client_cache_key: Optional[
            Tuple[str, Optional[str], str]
        ] = None
        self.last_request_time = 0.0
        self.request_count_minute = 0
        self.minute_start_time = time.time()
        self.stop_event: Optional[threading.Event] = None
        self._codex_sessions: Dict[Tuple[str, str, int], CodexChatSession] = {}
        self._openai_session: Optional[OpenAIResponsesSession] = None
        self._openai_session_identity: Optional[Tuple] = None

    def set_stop_event(
        self,
        stop_event: Optional[threading.Event],
    ) -> None:
        if stop_event is not self.stop_event:
            for session in self._codex_sessions.values():
                session.close()
            self._codex_sessions.clear()
            if self._openai_session is not None:
                self._openai_session.close()
                self._openai_session = None
        self.stop_event = stop_event

    def _wait(self, seconds: float) -> None:
        if seconds <= 0:
            return
        if self.stop_event is not None:
            if self.stop_event.wait(seconds):
                raise LLMRequestStopped()
            return
        time.sleep(seconds)

    @staticmethod
    def _openai_module() -> Any:
        import openai  # type: ignore

        return openai

    def _http_client(self, proxy: str) -> Any:
        import httpx  # type: ignore

        if not proxy:
            return httpx.Client()
        try:
            mounts = {
                'http://': httpx.HTTPTransport(proxy=proxy),
                'https://': httpx.HTTPTransport(proxy=proxy),
            }
            return httpx.Client(mounts=mounts)
        except Exception as error:
            self.logger.error(
                f"Failed to initialize proxy '{proxy}': {error}. "
                'Proceeding without proxy.'
            )
            return httpx.Client()

    @staticmethod
    def _api_key_for_profile(profile: LLMProfile) -> str:
        api_key = resolve_api_key(profile).strip()
        if profile.require_api_key and not api_key:
            raise LLMApiKeyRequiredError(profile.id, profile.name)
        return api_key

    def _client_api_key_for_profile(self, profile: LLMProfile) -> str:
        api_key = self._api_key_for_profile(profile)
        if not api_key:
            self.logger.debug(
                f'LLM profile "{profile.name or profile.id}" does not require '
                'an API key; using a dummy API key for OpenAI-compatible '
                'client initialization.'
            )
            return self.dummy_api_key
        return api_key

    def _initialize_client(self, profile: LLMProfile) -> Any:
        api_key = self._client_api_key_for_profile(profile)
        configured_base_url = str(profile.base_url or '').strip()
        base_url = _openai_sdk_base_url(configured_base_url) or None
        proxy = str(self.get_param_value('proxy') or '')
        cache_key = (api_key, base_url, proxy)
        if self.client is not None and self.client_cache_key == cache_key:
            return self.client

        if configured_base_url and base_url != configured_base_url:
            self.logger.warning(
                f'LLM profile "{profile.name or profile.id}" Base URL ends '
                f'with {_CHAT_COMPLETIONS_SUFFIX}; using its parent URL as '
                'the OpenAI-compatible API base.'
            )

        openai = self._openai_module()
        previous_client = self.client
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=self._http_client(proxy),
        )
        self.client_cache_key = cache_key
        if previous_client is not None:
            previous_client.close()
        return self.client

    def _respect_delay(self) -> None:
        current_time = time.time()
        rpm = self.get_param_value('max requests per minute')
        delay = self.get_param_value('delay')
        if rpm > 0:
            if current_time - self.minute_start_time >= 60:
                self.request_count_minute = 0
                self.minute_start_time = current_time
            if self.request_count_minute >= rpm:
                wait_time = 60.1 - (current_time - self.minute_start_time)
                if wait_time > 0:
                    self.logger.warning(
                        f'Global RPM limit ({rpm}) reached. Waiting '
                        f'{wait_time:.2f} seconds.'
                    )
                    self._wait(wait_time)
                self.request_count_minute = 0
                self.minute_start_time = time.time()

        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < delay:
            self._wait(delay - time_since_last_request)

        self.last_request_time = time.time()
        self.request_count_minute += 1

    def _request_ollama_native(
        self,
        profile: LLMProfile,
        api_args: Dict[str, Any],
        endpoint: str,
    ) -> LLMChatResult:
        """Send one non-streaming request to a local native Ollama API."""
        self._respect_delay()
        self._check_request_current(self.stop_event)
        client = self._http_client(str(self.get_param_value('proxy') or ''))
        try:
            payload = ollama_native_chat_payload(
                api_args,
                profile.ollama_context_length,
            )
            response = client.post(endpoint, json=payload, timeout=None)
            if response.status_code == 400 and payload.get('think'):
                self.logger.warning(
                    'Ollama rejected the requested thinking level; retrying '
                    'without explicit thinking control.'
                )
                payload.pop('think', None)
                response = client.post(endpoint, json=payload, timeout=None)
            if response.status_code == 400 and isinstance(payload.get('format'), dict):
                self.logger.warning(
                    'Ollama rejected native JSON schema mode; retrying with '
                    'generic JSON mode.'
                )
                payload['format'] = 'json'
                response = client.post(endpoint, json=payload, timeout=None)
            response.raise_for_status()
            data = response.json()
        finally:
            client.close()
        self._check_request_current(self.stop_event)
        if not isinstance(data, dict):
            raise RuntimeError('Ollama returned an invalid chat response.')
        if data.get('error'):
            raise RuntimeError(str(data['error']))
        message = data.get('message')
        content = message.get('content', '') if isinstance(message, dict) else ''
        prompt_tokens = int(data.get('prompt_eval_count') or 0)
        completion_tokens = int(data.get('eval_count') or 0)
        result = LLMChatResult(
            content=str(content or ''),
            usage=SimpleNamespace(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            finish_reason=str(data.get('done_reason') or ''),
        )
        if result.finish_reason.strip().lower() == 'length':
            raise LLMOutputLimitError(
                profile.id,
                profile.name,
                profile.max_tokens,
                str(profile.thinking_level or THINKING_AUTO),
            )
        return result

    def _responses_websocket_enabled(self) -> bool:
        value = os.environ.get(
            'BALLOONTRANS_RESPONSES_WEBSOCKET',
            os.environ.get('BALLOONTRANS_CODEX_WEBSOCKET'),
        )
        return value != '0'

    def _check_request_current(self, stop_event: Optional[threading.Event]) -> None:
        if stop_event is not self.stop_event or (stop_event is not None and stop_event.is_set()):
            raise LLMRequestStopped()

    def request_chat_completion(
        self,
        profile: LLMProfile,
        api_args: Dict[str, Any],
        *,
        codex_turn: Optional[CodexTurnState] = None,
    ) -> LLMChatResult:
        """Perform one request; feature owners decide whether to retry it."""
        # Throttling and client/session setup can overlap a run change. Never
        # adopt the replacement run's token for this request's existing inputs.
        stop_event = self.stop_event
        self._check_request_current(stop_event)
        unload_models_before_llm_request(self)
        if profile.backend == 'codex':
            if self._openai_session is not None:
                self._openai_session.close()
                self._openai_session = None
            from .codex import CodexChatSession, account, request_chat_completion
            self._respect_delay()
            self._check_request_current(stop_event)
            identity = (profile.id, str(api_args['model']), account.generation)
            proxy = str(self.get_param_value('proxy') or '')
            websocket = self._responses_websocket_enabled()
            session = self._codex_sessions.get(identity)
            if (session is None or session.closed or session.proxy != proxy
                    or session.websocket != websocket):
                for old_identity in tuple(self._codex_sessions):
                    if old_identity[2] != identity[2]:
                        self._codex_sessions.pop(old_identity).close()
                cache_key = session.cache_key if session is not None else str(uuid.uuid4())
                if session is not None:
                    session.close()
                session = self._codex_sessions[identity] = CodexChatSession(
                    cache_key, proxy, account_generation=identity[2], websocket=websocket)
            self._check_request_current(stop_event)
            result = request_chat_completion(
                profile, api_args, stop_event,
                session.cache_key, proxy, session=session, turn=codex_turn,
            )
            self._check_request_current(stop_event)
            return result
        if profile.backend != 'openai':
            raise LLMUserActionRequiredError('This LLM profile backend is unavailable.')
        ollama_endpoint = ollama_native_chat_url(profile)
        if profile.ollama_context_length > 0 and ollama_endpoint:
            return self._request_ollama_native(
                profile,
                api_args,
                ollama_endpoint,
            )
        openai = self._openai_module()
        client = self._initialize_client(profile)
        self._respect_delay()
        self._check_request_current(stop_event)
        # Only the direct OpenAI endpoint has a known Responses WS contract.
        # Check the SDK's resolved URL, including OPENAI_BASE_URL overrides.
        from .openai_responses import OpenAIResponsesSession
        base_url = str(getattr(client, 'base_url', '')).rstrip('/')
        model = str(api_args.get('model', ''))
        native = base_url == 'https://api.openai.com/v1'
        version = gpt_model_version(model)
        responses_model = ((version or (0, 0)) >= (4, 1) or model.startswith('gpt-4o')
                           or re.match(r'^o[1-9](?:-|$)', model) is not None)
        responses_model = responses_model and model not in ('o1-preview', 'o1-mini')
        use_responses = native and responses_model
        identity = (profile.id, model, self.client_cache_key)
        session = self._openai_session
        cache_key = (session.cache_key if session is not None and identity == self._openai_session_identity
                     else None)
        if session is not None and (not use_responses or session.closed or identity != self._openai_session_identity):
            session.close()
            self._openai_session = session = None
        if use_responses:
            if session is None:
                headers = {key: value for key, value in client.default_headers.items()
                           if isinstance(value, str) and key.lower() not in ('accept', 'content-type')}
                # Newer SDKs add auth during HTTP request preparation, outside
                # default_headers. Our WebSocket bypasses that preparation.
                headers['Authorization'] = f'Bearer {client.api_key}'
                self._openai_session = session = OpenAIResponsesSession(
                    base_url + '/responses', cache_key or str(uuid.uuid4()),
                    str(self.get_param_value('proxy') or ''), headers,
                    websocket=self._responses_websocket_enabled(),
                )
                self._openai_session_identity = identity
            self._check_request_current(stop_event)
            result = session.request_chat(api_args, profile, stop_event)
            if result is not None:
                self._check_request_current(stop_event)
                return result
        self._check_request_current(stop_event)
        try:
            completion = client.chat.completions.create(**api_args)
        except Exception as error:
            self._check_request_current(stop_event)
            if isinstance(error, getattr(openai, 'AuthenticationError')):
                raise LLMAuthenticationError(profile.id, profile.name) from error
            if isinstance(error, getattr(openai, 'APIStatusError')):
                raise LLMChatRequestError(error) from error
            raise

        self._check_request_current(stop_event)
        choice = next(iter(getattr(completion, 'choices', ())), None)
        message = getattr(choice, 'message', None)
        content = getattr(message, 'content', None)
        if content is None:
            content = getattr(choice, 'text', '')
        result = LLMChatResult(
            content=str(content or ''),
            usage=getattr(completion, 'usage', None),
            finish_reason=str(
                getattr(choice, 'finish_reason', '') or ''
            ),
            prompt_cache_diagnostics=getattr(completion, 'prompt_cache_diagnostics', None),
        )
        if result.finish_reason.strip().lower() == 'length':
            usage = format_completion_token_usage(result)
            model = str(api_args.get('model', '')).replace(
                '\r', ' '
            ).replace('\n', ' ')
            details = ', '.join(
                part for part in (
                    f'profile_id={profile.id!r}',
                    f'model={model!r}',
                    usage,
                    'finish_reason=length',
                    f'chars={len(result.content)}',
                    f'content={result.content!r}',
                )
                if part
            )
            self.logger.debug(f'LLM output-limited response: {details}')
            raise LLMOutputLimitError(
                profile.id,
                profile.name,
                profile.max_tokens,
                str(profile.thinking_level or THINKING_AUTO),
            )
        return result
