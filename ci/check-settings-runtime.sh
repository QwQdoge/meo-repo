#!/usr/bin/env bash
# Include the display transaction helper: it is loaded only when applying a
# display change, so checking the main window alone misses its ABI failures.
set -euo pipefail
for path in /usr/bin/meo-settings /usr/lib/meo-settings/meo-settings-display-transaction; do
  test -x "$path"
  resolved="$(ldd -r "$path" 2>&1)"
  if grep -E 'not found|undefined symbol:' <<<"$resolved"; then
    echo "Unresolved Settings ABI in $path" >&2
    exit 1
  fi
done
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software timeout 120 meo-settings --smoke
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software timeout 30 meo-welcome --show --smoke
echo 'PASS: Settings and display helper resolve against the installed KDE libraries'
