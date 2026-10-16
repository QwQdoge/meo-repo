#!/usr/bin/env bash
# Run only inside a disposable package builder/target, with mock authentication.
set -euo pipefail
for path in /usr/lib/libexec/plasma-login-greeter /usr/bin/plasma-login-wallpaper; do
  test -x "$path"
  elf="$(readelf -d "$path")"
  grep -F 'Shared library: [libPlasmaQuick.so.8]' <<<"$elf" >/dev/null
  if grep -E 'Shared library: \[(libPlasmaQuick\.so\.7|libPlasma\.so\.7|libkrdb\.so)' <<<"$elf"; then
    echo "Retired Plasma dependency in $path" >&2
    exit 1
  fi
  resolved="$(ldd -r "$path" 2>&1)"
  printf '%s\n%s\n' "$path" "$resolved"
  if grep -E 'not found|undefined symbol:' <<<"$resolved"; then
    exit 1
  fi
done
smoke_dir="$(mktemp -d)"
trap 'rm -rf -- "$smoke_dir"' EXIT
mkdir -m700 "$smoke_dir/runtime" "$smoke_dir/home"
status=0
env HOME="$smoke_dir/home" XDG_RUNTIME_DIR="$smoke_dir/runtime" \
  QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_OPENGL=software \
  timeout 8s /usr/lib/libexec/plasma-login-greeter --test >"$smoke_dir/greeter.log" 2>&1 || status=$?
cat "$smoke_dir/greeter.log"
test "$status" -eq 124
if grep -Ei 'Type .* unavailable|Cannot load library|module .* is not installed|Error loading QML|failed to load component|QQmlApplicationEngine failed' "$smoke_dir/greeter.log"; then
  exit 1
fi
echo 'PASS: login rendering resolves on Plasma 6.8 and mock greeter remains running'
