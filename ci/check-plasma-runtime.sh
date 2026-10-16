#!/usr/bin/env bash
# Run inside the installed target/container, never against the host session.
set -euo pipefail
plugin=/usr/lib/qt6/qml/Meo/System/libmeosystemplugin.so
test -s "$plugin"
elf="$(readelf -d "$plugin")"
grep -F 'Shared library: [libPlasma.so.8]' <<<"$elf" >/dev/null
paths=("$plugin")
if [ -x /usr/bin/meo-dynamic-colors ]; then
  paths+=(/usr/bin/meo-dynamic-colors)
fi
for path in "${paths[@]}"; do
  elf="$(readelf -d "$path")"
  if grep -E 'Shared library: \[(libkrdb\.so|libPlasma\.so\.7)' <<<"$elf"; then
    echo "Retired Plasma dependency in $path" >&2
    exit 1
  fi
  resolved="$(ldd "$path")"
  printf '%s\n%s\n' "$path" "$resolved"
  if grep -F 'not found' <<<"$resolved"; then
    echo "Unresolved runtime dependency in $path" >&2
    exit 1
  fi
done
echo 'PASS: installed Meo native runtime resolves on Plasma 6.8'
