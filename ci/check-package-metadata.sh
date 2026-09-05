#!/usr/bin/env bash
set -euo pipefail
directory="${1:?package directory is required}"
shopt -s nullglob
packages=("$directory"/*.pkg.tar.zst)
[ "${#packages[@]}" -gt 0 ] || { echo "No packages to check" >&2; exit 2; }
failed=0
for package in "${packages[@]}"; do
  # namcap does not consistently return nonzero for its E: diagnostics.
  if ! report="$(namcap "$package" 2>&1)"; then failed=1; fi
  printf '%s\n' "$report"
  if grep -Eq '^[^[:space:]]+ E:' <<<"$report"; then failed=1; fi
done
[ "$failed" = 0 ] || { echo "Package metadata errors block signing" >&2; exit 3; }
