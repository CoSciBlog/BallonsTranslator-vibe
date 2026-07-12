import importlib
from pathlib import Path
import sys


def test_vibe_version_tracks_upstream_package_metadata():
    from ballontranslator.utils.version import get_current_version

    assert get_current_version().startswith("1.5.7+vibe.")


def test_root_launch_shim_delegates_to_package_launcher():
    source = Path("launch.py").read_text(encoding="utf8")

    assert "from ballontranslator.launch import main" in source
    assert "main()" in source


def test_pinokio_metadata_uses_resources_icon():
    pinokio = Path("pinokio.json").read_text(encoding="utf8")
    launcher = Path("pinokio.js").read_text(encoding="utf8")

    assert "resources/icons/bottombar_translate.svg" in pinokio
    assert "resources/icons/bottombar_translate.svg" in launcher


def test_legacy_import_aliases_point_to_package_paths():
    import ballontranslator  # noqa: F401

    for legacy_name in ("utils", "modules", "ui"):
        module = importlib.import_module(legacy_name)
        assert legacy_name in sys.modules
        assert any("ballontranslator" in path for path in module.__path__)
