OLLAMA_DEFAULT_ENDPOINT = 'http://127.0.0.1:11434/v1'


def ollama_base_url(endpoint: str = '') -> str:
    base_url = str(endpoint or OLLAMA_DEFAULT_ENDPOINT).strip().rstrip('/')
    for suffix in ('/api/chat', '/api/tags', '/v1'):
        if base_url.endswith(suffix):
            base_url = base_url[:-len(suffix)].rstrip('/')
            break
    return base_url


def ollama_chat_endpoint(endpoint: str = '') -> str:
    return f'{ollama_base_url(endpoint)}/api/chat'


def ollama_tags_endpoint(endpoint: str = '') -> str:
    return f'{ollama_base_url(endpoint)}/api/tags'
