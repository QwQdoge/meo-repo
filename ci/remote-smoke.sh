#!/usr/bin/env bash
# Disposable Arch runner smoke test against packages.meoarch.org.
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
channel="${1:?stable or beta is required}"
candidate="${2:-}"
for file in meo.gpg meo-trusted meo-revoked; do
  [ -s "$repo_root/packages/meo-keyring/files/$file" ] || { echo "Missing public keyring file: $file" >&2; exit 2; }
  install -Dm644 "$repo_root/packages/meo-keyring/files/$file" "/usr/share/pacman/keyrings/$file"
done
pacman-key --init
pacman-key --populate archlinux meo

config="$(mktemp)"
trap 'rm -f -- "$config"' EXIT
cp -- /etc/pacman.conf "$config"
case "$channel" in
  stable)
    repositories=$'[meo]\nSigLevel = Required TrustedOnly\nServer = https://packages.meoarch.org/meo/os/x86_64'
    mapfile -t packages < <(python3 - "$repo_root/manifests/package-catalog.json" <<'PY'
import json,sys
catalog=json.load(open(sys.argv[1], encoding="utf-8"))
print(*catalog["packages"], sep="\n")
PY
)
    channel_package=meo-channel-stable
    ;;
  beta)
    case "$candidate" in meoui-qml|meo-icons|meo-desktop|meo-account|meo-settings|omnistore-bin) ;; *) echo "Invalid beta candidate" >&2; exit 2;; esac
    repositories=$'[meo-beta]\nSigLevel = Required TrustedOnly\nServer = https://packages.meoarch.org/meo-beta/os/x86_64\n\n[meo]\nSigLevel = Required TrustedOnly\nServer = https://packages.meoarch.org/meo/os/x86_64'
    packages=("$candidate")
    channel_package=meo-channel-beta
    ;;
  *) echo "Invalid channel" >&2; exit 2 ;;
esac
printf '\n%s\n' "$repositories" >>"$config"
pacman --config "$config" -Syy --noconfirm
mapfile -t resolved < <(pacman-conf --config "$config" --repo-list)
if [ "$channel" = beta ]; then
  beta_index=-1; stable_index=-1
  for index in "${!resolved[@]}"; do
    [ "${resolved[$index]}" = meo-beta ] && beta_index="$index"
    [ "${resolved[$index]}" = meo ] && stable_index="$index"
  done
  [ "$beta_index" -ge 0 ] && [ "$stable_index" -gt "$beta_index" ] || { echo "Invalid beta repository priority" >&2; exit 3; }
  ! pacman --config "$config" -Si meo-beta/meo-release >/dev/null 2>&1 || {
    echo "Beta overlay must not duplicate the Stable control package meo-release" >&2; exit 3;
  }
  pacman --config "$config" -Si meo/meo-release >/dev/null || {
    echo "Stable fallback does not provide meo-release" >&2; exit 3;
  }
fi
pacman --config "$config" -S --needed --noconfirm \
  meo-keyring meo-mirrorlist "$channel_package" meo-release "${packages[@]}"
pacman-conf --repo-list
