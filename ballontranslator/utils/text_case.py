def apply_text_case(text: str, text_case: str = "normal") -> str:
    if not isinstance(text, str):
        return text
    if text_case == "upper":
        return text.upper()
    if text_case == "lower":
        return text.lower()
    return text
