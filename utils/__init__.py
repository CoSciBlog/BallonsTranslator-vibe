"""Compatibility package for legacy ``utils`` imports."""

from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parent
_PACKAGE_DIR = _ROOT_DIR.parent / "ballontranslator" / "utils"

__path__ = [str(_ROOT_DIR), str(_PACKAGE_DIR)]
