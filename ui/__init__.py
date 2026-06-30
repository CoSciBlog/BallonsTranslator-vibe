"""Compatibility package for legacy ``ui`` imports."""

from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parent
_PACKAGE_DIR = _ROOT_DIR.parent / "ballontranslator" / "ui"

__path__ = [str(_PACKAGE_DIR), str(_ROOT_DIR)]
