#!/usr/bin/env bash
# Headless smoke for the native Bottles package: the CLI imports the whole
# backend (including the bundled patool), and the GUI's vkBasalt dialog
# imports the bundled vkbasalt-cli module at startup.
set -euo pipefail

smoke_home="$(mktemp -d)"
trap 'rm -rf -- "$smoke_home"' EXIT
HOME="$smoke_home" XDG_DATA_HOME="$smoke_home/.local/share" \
  timeout 60 bottles-cli --help >/dev/null
python3 - <<'PY'
import sys
sys.path.insert(1, "/usr/share/bottles")
import patoolib  # noqa: F401
from vkbasalt.lib import ParseConfig, parse  # noqa: F401
PY
# The packaged frontend must not carry the upstream sandbox-only guards.
if grep -rqF 'running_under_sandbox():' /usr/share/bottles/bottles/frontend/windows/window.py; then
  echo "Bottles still refuses to start outside a sandbox" >&2
  exit 1
fi
echo "bottles runtime smoke passed"
