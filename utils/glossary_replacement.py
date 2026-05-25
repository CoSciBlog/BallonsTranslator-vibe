import html
import re
from typing import Dict, List, Tuple


GlossaryEntry = Dict[str, str]
Replacement = Tuple[str, str]
GLOSSARY_ENTRY_FIELDS = ("entries", "reference_entries")


def parse_glossary_entries(text: str) -> List[GlossaryEntry]:
    entries = []
    for line in (text or "").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#") or "=>" not in clean:
            continue
        source, rest = [part.strip() for part in clean.split("=>", 1)]
        note = ""
        if "#" in rest:
            rest, note = [part.strip() for part in rest.split("#", 1)]
        category = "term"
        category_match = re.search(r"\[([^\]]+)\]\s*$", rest)
        if category_match:
            category = category_match.group(1).strip() or "term"
            rest = rest[: category_match.start()].strip()
        entries.append(
            {
                "source": source,
                "target": rest,
                "category": category,
                "note": note,
            }
        )
    return entries


def _entry_key(entry: GlossaryEntry) -> str:
    return (entry.get("source") or "").casefold()


def _append_replacement(replacements: List[Replacement], old_target: str, new_target: str) -> None:
    old_target = (old_target or "").strip()
    new_target = (new_target or "").strip()
    if not old_target or not new_target or old_target == new_target:
        return
    if (old_target, new_target) not in replacements:
        replacements.append((old_target, new_target))


def build_glossary_replacements(old_glossary: Dict[str, str], new_glossary: Dict[str, str]) -> List[Replacement]:
    old_entries = parse_glossary_entries((old_glossary or {}).get("entries", ""))
    new_entries = parse_glossary_entries((new_glossary or {}).get("entries", ""))

    old_by_source = {_entry_key(entry): entry for entry in old_entries if _entry_key(entry)}
    replacements: List[Replacement] = []

    for idx, new_entry in enumerate(new_entries):
        old_entry = old_by_source.get(_entry_key(new_entry))
        if old_entry is None and idx < len(old_entries):
            old_entry = old_entries[idx]
        if old_entry is None:
            continue
        _append_replacement(
            replacements,
            old_entry.get("target", ""),
            new_entry.get("target", ""),
        )

    replacements.sort(key=lambda item: len(item[0]), reverse=True)
    return replacements


def count_glossary_matches(
    glossary: Dict[str, str],
    pattern: re.Pattern,
    match_source: bool,
    match_target: bool,
) -> int:
    if pattern is None:
        return 0

    count = 0
    for field in GLOSSARY_ENTRY_FIELDS:
        for entry in parse_glossary_entries((glossary or {}).get(field, "")):
            if match_source:
                count += sum(1 for _ in pattern.finditer(entry.get("source", "")))
            if match_target:
                count += sum(1 for _ in pattern.finditer(entry.get("target", "")))
    return count


def replace_glossary_matches(
    glossary: Dict[str, str],
    pattern: re.Pattern,
    replacement: str,
    replace_source: bool,
    replace_target: bool,
) -> Tuple[Dict[str, str], int]:
    updated = dict(glossary or {})
    if pattern is None:
        return updated, 0

    replacement_count = 0
    for field in GLOSSARY_ENTRY_FIELDS:
        original_text = updated.get(field, "")
        lines = []
        for line in (original_text or "").splitlines():
            parsed = parse_glossary_entries(line)
            if len(parsed) != 1:
                lines.append(line)
                continue

            entry = parsed[0]
            changed = False
            if replace_source:
                entry["source"], count = pattern.subn(replacement, entry["source"])
                replacement_count += count
                changed |= count > 0
            if replace_target:
                entry["target"], count = pattern.subn(replacement, entry["target"])
                replacement_count += count
                changed |= count > 0

            if not changed:
                lines.append(line)
                continue

            rendered = f'{entry["source"]} => {entry["target"]}'
            category = entry.get("category", "")
            note = entry.get("note", "")
            if category:
                rendered += f" [{category}]"
            if note:
                rendered += f" # {note}"
            lines.append(rendered)
        updated[field] = "\n".join(lines)

    return updated, replacement_count


def _term_pattern(term: str) -> re.Pattern:
    escaped = re.escape(term)
    prefix = r"(?<!\w)" if term and term[0].isalnum() else ""
    suffix = r"(?!\w)" if term and term[-1].isalnum() else ""
    return re.compile(f"{prefix}{escaped}{suffix}")


def apply_glossary_replacements_to_text(text: str, replacements: List[Replacement]) -> Tuple[str, int]:
    if not text or not replacements:
        return text, 0

    updated = text
    total = 0
    for old_target, new_target in replacements:
        updated, count = _term_pattern(old_target).subn(new_target, updated)
        total += count

        old_escaped = html.escape(old_target, quote=False)
        new_escaped = html.escape(new_target, quote=False)
        if old_escaped != old_target:
            updated, count = _term_pattern(old_escaped).subn(new_escaped, updated)
            total += count

    return updated, total
