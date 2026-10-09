#!/usr/bin/env sh

set -eu

fail() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

resolve_script_dir() {
    script=$0

    case "$script" in
        */*) ;;
        *)
            found=$(command -v "$script" 2>/dev/null || true)
            [ -n "$found" ] && script=$found
            ;;
    esac

    script_dir=$(CDPATH= cd "$(dirname "$script")" && pwd -P)
    printf '%s\n' "$script_dir"
}

APP_DIR=$(resolve_script_dir)
VENV_DIR="${APP_DIR}/.venv"
VENV_PYTHON="${VENV_DIR}/bin/python"
ACTIVATE_SCRIPT="${VENV_DIR}/bin/activate"

cd "$APP_DIR"

[ -x "$VENV_PYTHON" ] || fail "Missing project virtual environment ${VENV_DIR}. Run the macOS/Linux install command from README first."

if [ -f "$ACTIVATE_SCRIPT" ]; then
    # Keep subprocess behavior consistent with a normal user-activated venv.
    . "$ACTIVATE_SCRIPT"
fi

exec "$VENV_PYTHON" -m ballontranslator "$@"
