import os
from pathlib import Path
from types import SimpleNamespace

from ballontranslator.launch import main


args = SimpleNamespace(frozen=False, update=False, repair_runtime=False)


def should_prepare_environment(runtime_profile_file=None):
    """Compatibility helper kept for Vibe runtime-environment tests."""

    if getattr(args, "frozen", False):
        return False
    if getattr(args, "update", False) or getattr(args, "repair_runtime", False):
        return True
    if os.environ.get("BALLOONTRANS_FORCE_RUNTIME_CHECK") == "1":
        return True
    return not Path(runtime_profile_file or ".runtime_profile.json").exists()


if __name__ == "__main__":
    main()
