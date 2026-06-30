import textwrap


def wrap_tooltip(text: str, width: int = 92) -> str:
    if not text:
        return text

    wrapped_lines = []
    for line in str(text).splitlines() or [str(text)]:
        if not line:
            wrapped_lines.append(line)
            continue
        wrapped_lines.append(
            textwrap.fill(
                line,
                width=width,
                break_long_words=False,
                break_on_hyphens=False,
            )
        )
    return "\n".join(wrapped_lines)
