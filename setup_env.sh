#!/usr/bin/env bash
# Provided environment setup for macOS/Linux. Run beside ImageDescriptionServer.py and the requirements.
# Students do not need to read or modify this file.
set -euo pipefail
cd "$(dirname "$0")"
exec > >(tee setup.log) 2>&1
trap 'echo "Setup failed. Send setup.log to the TA if retrying does not help."' ERR

# Keep tools, Python and packages inside this assignment folder.
for name in $(env | sed -n 's/^\(UV_[A-Za-z0-9_]*\)=.*/\1/p'); do unset "$name"; done
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV CONDA_PREFIX CARGO_DIST_FORCE_INSTALL_DIR
ROOT="$(pwd -P)"
UV_VERSION="0.10.9"
PYTHON_VERSION="3.11.15"
UV="$ROOT/.tools/uv/uv"
PYTHON="$ROOT/.venv/bin/python"
export UV_UNMANAGED_INSTALL="$ROOT/.tools/uv"
export UV_PYTHON_INSTALL_DIR="$ROOT/.runtime/python" UV_CACHE_DIR="$ROOT/.runtime/uv-cache"
export UV_NO_CONFIG=true UV_MANAGED_PYTHON=true UV_NATIVE_TLS=true
mkdir -p .tools
if [ ! -f ImageDescriptionServer.py ] || [ ! -f requirements.lock.txt ]; then
    echo "ImageDescriptionServer.py or requirements.lock.txt is missing. Extract the complete assignment ZIP first."
    exit 1
fi

echo "[1/4] Preparing uv $UV_VERSION..."
if [ ! -x "$UV" ]; then
    curl -fLsS --connect-timeout 20 "https://astral.sh/uv/$UV_VERSION/install.sh" -o .tools/uv-install.sh
    sh .tools/uv-install.sh
fi
"$UV" --version
if [ "$("$UV" --version | awk '{print $2}')" != "$UV_VERSION" ]; then
    echo "The local uv version differs from the course version. Contact the TA."
    exit 1
fi

echo "[2/4] Preparing Python $PYTHON_VERSION and .venv..."
# Reuse a matching environment; never delete or rebuild an existing one.
if [ -e .venv ] || [ -L .venv ]; then
    if [ ! -f .venv/pyvenv.cfg ] || [ "$("$PYTHON" --version 2>/dev/null)" != "Python $PYTHON_VERSION" ]; then
        echo "The existing .venv is incompatible. Contact the TA; it was left unchanged."
        exit 1
    fi
fi
"$UV" python install --managed-python --no-bin --no-registry "$PYTHON_VERSION"
if [ ! -d .venv ]; then
    "$UV" venv --managed-python --python "$PYTHON_VERSION" "$ROOT/.venv"
fi

echo "[3/4] Installing the pinned CPU dependencies..."
# PyPI supplies a CPU torch wheel for Linux ARM; other targets use uv's CPU selection.
if [ "$(uname -s)" = Linux ] && [ "$(uname -m)" != x86_64 ]; then
    "$UV" pip install --python "$PYTHON" --only-binary :all: --reinstall-package torch -r requirements.lock.txt
else
    "$UV" pip install --python "$PYTHON" --only-binary :all: --reinstall-package torch --torch-backend cpu -r requirements.lock.txt
fi

echo "[4/4] Checking dependencies..."
"$UV" pip check --python "$PYTHON"
echo "Setup complete. Use .venv/bin/python for this assignment; activation is not needed."
echo "Check the AI with: .venv/bin/python ImageDescriptionServer.py --check-ai ./test_images/cat.jpg"
echo "Log: $ROOT/setup.log"
