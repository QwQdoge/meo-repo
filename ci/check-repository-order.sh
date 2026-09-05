#!/usr/bin/env bash
set -euo pipefail
config="${1:?pacman configuration is required}"
channel="${2:?stable or beta is required}"
case "$channel" in
  stable) expected=meo ;;
  beta) expected=$'meo-beta\nmeo' ;;
  *) echo "Invalid channel" >&2; exit 2 ;;
esac
# Capture status before filtering so parser failures cannot become an empty
# or partially valid repository list.
resolved="$(pacman-conf --config "$config" --repo-list)"
actual="$(printf '%s\n' "$resolved" | sed -n '/^meo\($\|-\)/p')"
[ "$actual" = "$expected" ] || {
  echo "Configured Meo repositories do not match $channel: $actual" >&2
  exit 3
}
printf '%s\n' "$resolved"
