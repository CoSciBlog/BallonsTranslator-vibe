import re


OLLAMA_DEFAULT_ENDPOINT = 'http://127.0.0.1:11434/v1'


def ollama_model_matches_query(model_name: str, query: str = '') -> bool:
    name = str(model_name or '').casefold()
    terms = str(query or '').casefold().split()
    return all(term in name for term in terms)


def ollama_model_parameter_size(model_name: str = '', declared_size: str = '') -> str:
    """Return a normalized parameter-size label such as 12B, 1.5B, or 335M."""
    pattern = re.compile(r'(?<![\d.])(\d+(?:\.\d+)?)\s*([mMbB])(?![A-Za-z])')
    for value in (model_name, declared_size):
        match = pattern.search(str(value or ''))
        if match:
            number = float(match.group(1))
            display = str(int(number)) if number.is_integer() else f'{number:g}'
            return f'{display}{match.group(2).upper()}'
    return ''


def ollama_parameter_size_sort_key(size: str):
    normalized = ollama_model_parameter_size(declared_size=size)
    if not normalized:
        return (1, float('inf'), str(size).casefold())
    value = float(normalized[:-1])
    if normalized.endswith('M'):
        value /= 1000
    return (0, value, normalized.casefold())


def ollama_model_matches_filters(
    model_name: str,
    query: str = '',
    model_parameter_size: str = '',
    parameter_size_filter: str = '',
    reasoning_status: str = 'unknown',
    reasoning_filter: str = '',
    rating: int = 3,
    minimum_rating: int = 0,
) -> bool:
    if not ollama_model_matches_query(model_name, query):
        return False
    if parameter_size_filter:
        actual_size = ollama_model_parameter_size(
            model_name=model_parameter_size or model_name
        )
        expected_size = ollama_model_parameter_size(declared_size=parameter_size_filter)
        if actual_size != expected_size:
            return False
    if reasoning_filter and str(reasoning_status).casefold() != str(reasoning_filter).casefold():
        return False
    try:
        if int(rating) < int(minimum_rating):
            return False
    except (TypeError, ValueError):
        return False
    return True


def ollama_model_sort_value(
    column: str,
    model_name: str = '',
    reasoning_status: str = 'unknown',
    rating: int = 0,
):
    column = str(column or '').casefold()
    if column == 'model':
        return str(model_name or '').casefold()
    if column == 'reasoning':
        return {'no': 0, 'unknown': 1, 'yes': 2}.get(
            str(reasoning_status or '').casefold(), 1
        )
    if column == 'rating':
        try:
            return max(1, min(5, int(rating)))
        except (TypeError, ValueError):
            return 0
    return ''


def ollama_base_url(endpoint: str = '') -> str:
    base_url = str(endpoint or OLLAMA_DEFAULT_ENDPOINT).strip().rstrip('/')
    for suffix in ('/api/chat', '/api/tags', '/api/show', '/v1'):
        if base_url.endswith(suffix):
            base_url = base_url[:-len(suffix)].rstrip('/')
            break
    return base_url


def ollama_chat_endpoint(endpoint: str = '') -> str:
    return f'{ollama_base_url(endpoint)}/api/chat'


def ollama_tags_endpoint(endpoint: str = '') -> str:
    return f'{ollama_base_url(endpoint)}/api/tags'


def ollama_show_endpoint(endpoint: str = '') -> str:
    return f'{ollama_base_url(endpoint)}/api/show'


def ollama_thinking_capability(capabilities):
    """Return True/False for declared capabilities, or None when unavailable."""
    if not isinstance(capabilities, list):
        return None
    return any(str(capability).casefold() == 'thinking' for capability in capabilities)
