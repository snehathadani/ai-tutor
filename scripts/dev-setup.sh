#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

VENV_DIR=backend/.venv
VENV_PY="$VENV_DIR/bin/python"
PYTHON="${PYTHON:-}"

if [ ! -x "$VENV_PY" ]; then
    if command -v uv >/dev/null 2>&1; then
        echo "==> creating $VENV_DIR with uv"
        if ! uv venv --python "${PYTHON:-python3}" "$VENV_DIR"; then
            if [ -z "$PYTHON" ]; then
                echo "==> uv venv failed, retrying with default python3"
                uv venv --python python3 "$VENV_DIR" || true
            fi
        fi
    fi

    if [ ! -x "$VENV_PY" ]; then
        for cand in ${PYTHON:-} python3 python3.12 python3.11 python3.10 python; do
            [ -n "$cand" ] || continue
            if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import ensurepip' >/dev/null 2>&1; then
                echo "==> creating $VENV_DIR with $cand"
                "$cand" -m venv "$VENV_DIR"
                break
            fi
        done
    fi

    if [ ! -x "$VENV_PY" ]; then
        echo "error: could not create $VENV_DIR" >&2
        echo "On Debian/Ubuntu install the venv module (apt install python3.12-venv); installing uv also works." >&2
        exit 1
    fi
else
    echo "==> $VENV_DIR already exists, reusing it"
fi

if ! "$VENV_PY" -m pip --version >/dev/null 2>&1; then
    echo "==> pip missing in $VENV_DIR, bootstrapping"
    if command -v uv >/dev/null 2>&1; then
        uv pip install --python "$VENV_PY" pip || echo "warning: could not bootstrap pip via uv" >&2
    else
        "$VENV_PY" -m ensurepip --upgrade || echo "warning: could not bootstrap pip via ensurepip" >&2
    fi
fi

if command -v uv >/dev/null 2>&1; then
    echo "==> installing backend requirements (+ dev deps) with uv"
    uv pip install --python "$VENV_PY" -r backend/requirements.txt -r backend/requirements-dev.txt
else
    echo "==> installing backend requirements (+ dev deps) with pip"
    "$VENV_PY" -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
fi

echo "==> venv: $VENV_DIR"
"$VENV_PY" --version
if "$VENV_PY" -m pip --version >/dev/null 2>&1; then
    echo "==> pip: present in venv"
else
    echo "==> pip: not present in venv"
fi
echo "==> done; activate with: source backend/.venv/bin/activate"
