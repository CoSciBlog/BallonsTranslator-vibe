"""Compatibility package for legacy ``modules`` imports."""

from pathlib import Path

from ballontranslator.modules import *  # noqa: F403

_ROOT_DIR = Path(__file__).resolve().parent
_PACKAGE_DIR = _ROOT_DIR.parent / "ballontranslator" / "modules"

__path__ = [str(_ROOT_DIR), str(_PACKAGE_DIR)]
