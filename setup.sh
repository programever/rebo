#!/usr/bin/env bash
# One-time setup: a private Python environment with the three libraries we need.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
echo "ok: .venv is ready"
