import json
import os
import os.path as osp
import re
from collections import OrderedDict
from typing import Dict, Iterable, List, Tuple


TEXT_EXTENSIONS = {".txt", ".md"}
PROJECT_PREFIX = "imgtrans_"
PROJECT_SUFFIX = ".json"

COMMON_CAPITALIZED_WORDS = {
    "A", "An", "And", "Are", "As", "At", "But", "By", "Chapter", "For", "From",
    "He", "Her", "His", "I", "If", "In", "Into", "It", "Its", "Me", "My", "No",
    "Of", "On", "Or", "Our", "Page", "She", "So", "That", "The", "Their",
    "They", "This", "To", "We", "What", "When", "Where", "Who", "Why", "With",
    "You", "Your",
}

PLACE_HINTS = {
    "academy", "bridge", "castle", "city", "district", "forest", "gate", "harbor",
    "harbour", "hill", "inn", "island", "kingdom", "lake", "mount", "mountain",
    "palace", "park", "river", "road", "school", "sea", "shrine", "station",
    "street", "temple", "tower", "town", "village",
}

ORG_HINTS = {
    "academy", "association", "church", "clan", "club", "company", "council",
    "guild", "institute", "office", "school", "squad", "team",
}

TITLE_HINTS = {
    "captain", "chief", "doctor", "dr", "emperor", "empress", "general", "king",
    "lady", "lord", "master", "miss", "mr", "mrs", "ms", "prince", "princess",
    "professor", "queen", "saint", "sir",
}


def normalize_glossary_payload(payload) -> Dict[str, str]:
    if isinstance(payload, str):
        return {"entries": payload, "prompt": "", "reference_entries": ""}
    if not isinstance(payload, dict):
        return {"entries": "", "prompt": "", "reference_entries": ""}
    return {
        "entries": payload.get("entries", payload.get("text", payload.get("glossary", ""))) or "",
        "prompt": payload.get("prompt", "") or "",
        "reference_entries": payload.get("reference_entries", payload.get("reference", "")) or "",
    }


def iter_glossary_source_files(folder: str, include_subfolders: bool = False) -> Iterable[str]:
    if include_subfolders:
        for root, _, files in os.walk(folder):
            for name in files:
                path = osp.join(root, name)
                if _is_source_file(path):
                    yield path
        return

    for name in os.listdir(folder):
        path = osp.join(folder, name)
        if osp.isfile(path) and _is_source_file(path):
            yield path


def _is_source_file(path: str) -> bool:
    name = osp.basename(path)
    ext = osp.splitext(name)[1].lower()
    return (
        name == "glossary.json"
        or (name.startswith(PROJECT_PREFIX) and name.endswith(PROJECT_SUFFIX))
        or ext in TEXT_EXTENSIONS
    )


def build_glossary_from_translated_folder(folder: str, include_subfolders: bool = False) -> Dict[str, str]:
    entries: "OrderedDict[Tuple[str, str], str]" = OrderedDict()
    source_count = 0
    text_count = 0

    for path in iter_glossary_source_files(folder, include_subfolders):
        source_count += 1
        for text, source_hint in _texts_from_file(path):
            text_count += 1
            for term, category in extract_reference_terms(text):
                key = (term.casefold(), category)
                if key not in entries:
                    rel = osp.relpath(path, folder)
                    note = f"template: {rel}"
                    entries[key] = format_glossary_line(term, term, category, note)

            for source, target, category, note in _explicit_entries_from_text(text):
                key = (source.casefold(), category)
                if key not in entries:
                    suffix = f"; {source_hint}" if source_hint else ""
                    entries[key] = format_glossary_line(source, target, category, note + suffix if note else source_hint)

    return {
        "entries": "\n".join(entries.values()),
        "prompt": "",
        "reference_entries": "",
        "source_count": source_count,
        "text_count": text_count,
    }


def build_glossary_from_project_text(project, pages: Iterable[str] = None) -> Dict[str, str]:
    entries: "OrderedDict[Tuple[str, str], str]" = OrderedDict()
    page_names = list(pages) if pages is not None else list(getattr(project, "pages", {}).keys())
    text_count = 0

    for page_name in page_names:
        blocks = getattr(project, "pages", {}).get(page_name, [])
        for block in blocks:
            text = ""
            if hasattr(block, "get_text"):
                text = block.get_text()
            elif isinstance(block, dict):
                text = block.get("text", "")
            if not isinstance(text, str) or not text.strip():
                continue
            text_count += 1
            for term, category in extract_reference_terms(text):
                key = (term.casefold(), category)
                if key not in entries:
                    note = f"gloss scan: {page_name}"
                    entries[key] = format_glossary_line(term, term, category, note)

    return {
        "entries": "\n".join(entries.values()),
        "prompt": "",
        "reference_entries": "",
        "source_count": len(page_names),
        "text_count": text_count,
    }


def merge_glossary_entry_text(existing: str, incoming: str) -> str:
    merged: "OrderedDict[Tuple[str, str], str]" = OrderedDict()
    for line in (existing or "").splitlines():
        key = _glossary_line_key(line) or ("raw", line.strip())
        if key is not None and key not in merged:
            merged[key] = line.strip()
    for line in (incoming or "").splitlines():
        key = _glossary_line_key(line) or ("raw", line.strip())
        if key is not None and key not in merged:
            merged[key] = line.strip()
    return "\n".join(line for line in merged.values() if line)


def _glossary_line_key(line: str):
    for source, _target, category, _note in _explicit_entries_from_text(line):
        return source.casefold(), (category or "term").casefold()
    return None


def _texts_from_file(path: str) -> Iterable[Tuple[str, str]]:
    name = osp.basename(path)
    ext = osp.splitext(name)[1].lower()
    if name == "glossary.json":
        with open(path, "r", encoding="utf8") as f:
            payload = normalize_glossary_payload(json.load(f))
        for key in ("entries", "reference_entries"):
            if payload.get(key):
                yield payload[key], key
        return

    if name.startswith(PROJECT_PREFIX) and name.endswith(PROJECT_SUFFIX):
        with open(path, "r", encoding="utf8") as f:
            payload = json.load(f)
        pages = payload.get("pages", {})
        if isinstance(pages, dict):
            for blocks in pages.values():
                if not isinstance(blocks, list):
                    continue
                for block in blocks:
                    if isinstance(block, dict):
                        for key in ("translation", "text", "rich_text", "translation_draft"):
                            value = block.get(key)
                            if isinstance(value, str) and value.strip():
                                yield _strip_markup(value), key
        return

    if ext in TEXT_EXTENSIONS:
        with open(path, "r", encoding="utf8") as f:
            yield f.read(), ext.lstrip(".")


def _strip_markup(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _explicit_entries_from_text(text: str) -> Iterable[Tuple[str, str, str, str]]:
    for line in (text or "").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#") or "=>" not in clean:
            continue
        source, rest = [part.strip() for part in clean.split("=>", 1)]
        note = ""
        if "#" in rest:
            rest, note = [part.strip() for part in rest.split("#", 1)]
        category = "term"
        match = re.search(r"\[([^\]]+)\]\s*$", rest)
        if match:
            category = match.group(1).strip() or "term"
            rest = rest[: match.start()].strip()
        if source and rest:
            yield source, rest, category, note


def extract_reference_terms(text: str) -> List[Tuple[str, str]]:
    cleaned = _strip_markup(text)
    candidates: List[Tuple[str, str]] = []
    pattern = re.compile(
        r"\b(?:[A-Z][a-zA-Z'.-]{1,}|[A-Z]{2,})(?:\s+(?:of|the|de|del|van|von|[A-Z][a-zA-Z'.-]{1,}|[A-Z]{2,})){0,4}\b"
    )
    for match in pattern.finditer(cleaned):
        term = _clean_term(match.group(0))
        if not _valid_term(term):
            continue
        candidates.append((term, classify_reference_term(term)))
    return _dedupe_terms(candidates)


def _clean_term(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip(" \t\r\n\"'.,!?;:()[]{}"))


def _valid_term(term: str) -> bool:
    if len(term) < 3 or len(term) > 80:
        return False
    words = term.split()
    if len(words) == 1 and words[0] in COMMON_CAPITALIZED_WORDS:
        return False
    if all(word in COMMON_CAPITALIZED_WORDS for word in words):
        return False
    if re.search(r"\d", term):
        return False
    return True


def classify_reference_term(term: str) -> str:
    words = {word.strip(".,'").casefold() for word in term.split()}
    if words & TITLE_HINTS:
        return "title"
    if words & PLACE_HINTS:
        return "place"
    if words & ORG_HINTS:
        return "organization"
    return "character" if len(term.split()) <= 3 else "term"


def _dedupe_terms(candidates: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    seen = set()
    result = []
    for term, category in candidates:
        key = (term.casefold(), category)
        if key in seen:
            continue
        seen.add(key)
        result.append((term, category))
    return result


def format_glossary_line(source: str, target: str, category: str = "term", note: str = "") -> str:
    line = f"{source.strip()} => {target.strip()} [{(category or 'term').strip()}]"
    note = (note or "").strip()
    if note:
        line += f" # {note}"
    return line
