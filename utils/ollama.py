OLLAMA_DEFAULT_ENDPOINT = 'http://127.0.0.1:11434/v1'


def ollama_model_matches_query(model_name: str, query: str = '') -> bool:
    name = str(model_name or '').casefold()
    terms = str(query or '').casefold().split()
    return all(term in name for term in terms)


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
