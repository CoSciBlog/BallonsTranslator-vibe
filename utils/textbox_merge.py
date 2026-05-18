from typing import Iterable, List, Sequence


def join_textbox_texts(texts: Iterable[str], separator: str = "\n") -> str:
    parts = []
    for text in texts:
        text = (text or "").strip()
        if text:
            parts.append(text)
    return separator.join(parts)


def union_xywh_rects(rects: Iterable[Sequence[float]]) -> List[int]:
    rects = list(rects)
    if not rects:
        return [0, 0, 0, 0]

    x1 = min(rect[0] for rect in rects)
    y1 = min(rect[1] for rect in rects)
    x2 = max(rect[0] + rect[2] for rect in rects)
    y2 = max(rect[1] + rect[3] for rect in rects)
    return [int(round(x1)), int(round(y1)), int(round(x2 - x1)), int(round(y2 - y1))]
