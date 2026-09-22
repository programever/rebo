#!/usr/bin/env bash
# One rebo run. Same command by hand or from the systemd timer.
#   ./run.sh                 build today and publish the page
#   ./run.sh --dry-run       build everything, publish nothing
#   ./run.sh --skip-voice    text only, no sound, no publish
#   ./run.sh --publish-only  rebuild the page from days already on this box
#   ./run.sh --force         plan today again from the same place
#   ./run.sh --date 2026-09-22
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "no .venv — run ./setup.sh first" >&2
  exit 2
fi
exec .venv/bin/python -m pipeline.main "$@"
