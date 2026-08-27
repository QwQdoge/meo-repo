#!/usr/bin/env bash
# Configure signed current Stable + sparse Beta only inside a disposable Arch
# build container so beta candidate dependencies resolve exactly as users see.
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
for file in meo.gpg meo-trusted meo-revoked; do
  [ -s "$repo_root/packages/meo-keyring/files/$file" ] || { echo "Missing public keyring file: $file" >&2; exit 2; }
  install -Dm644 "$repo_root/packages/meo-keyring/files/$file" "/usr/share/pacman/keyrings/$file"
done
pacman-key --init
pacman-key --populate meo
install -Dm644 /dev/stdin /etc/pacman.d/meo-ci-build.conf <<'EOF'
[meo-beta]
SigLevel = Required TrustedOnly
Server = https://packages.meoarch.org/meo-beta/os/x86_64

[meo]
SigLevel = Required TrustedOnly
Server = https://packages.meoarch.org/meo/os/x86_64
EOF
printf '\n# Disposable CI-only Meo dependency source.\nInclude = /etc/pacman.d/meo-ci-build.conf\n' >>/etc/pacman.conf
pacman -Syy --noconfirm
mapfile -t repositories < <(pacman-conf --repo-list)
beta=-1; stable=-1
for index in "${!repositories[@]}"; do
  [ "${repositories[$index]}" = meo-beta ] && beta="$index"
  [ "${repositories[$index]}" = meo ] && stable="$index"
done
[ "$beta" -ge 0 ] && [ "$stable" -gt "$beta" ] || { echo "Invalid beta dependency repository order" >&2; exit 3; }
