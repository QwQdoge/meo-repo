#!/usr/bin/env bash
# Configure the signed public repositories inside a disposable Arch build
# container so sparse candidate dependencies resolve exactly as users see.
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
channel="${1:?stable or beta channel is required}"
case "$channel" in stable|beta) ;; *) echo "Invalid channel" >&2; exit 2 ;; esac
for file in meo.gpg meo-trusted meo-revoked; do
  [ -s "$repo_root/packages/meo-keyring/files/$file" ] || { echo "Missing public keyring file: $file" >&2; exit 2; }
  install -Dm644 "$repo_root/packages/meo-keyring/files/$file" "/usr/share/pacman/keyrings/$file"
done
pacman-key --init
pacman-key --populate meo
if [ "$channel" = beta ]; then
  install -Dm644 /dev/stdin /etc/pacman.d/meo-ci-build.conf <<'EOF'
[meo-beta]
SigLevel = Required TrustedOnly
Server = https://packages.meoarch.org/meo-beta/os/x86_64

[meo]
SigLevel = Required TrustedOnly
Server = https://packages.meoarch.org/meo/os/x86_64
EOF
else
  install -Dm644 /dev/stdin /etc/pacman.d/meo-ci-build.conf <<'EOF'
[meo]
SigLevel = Required TrustedOnly
Server = https://packages.meoarch.org/meo/os/x86_64
EOF
fi
printf '\n# Disposable CI-only Meo dependency source.\nInclude = /etc/pacman.d/meo-ci-build.conf\n' >>/etc/pacman.conf
pacman -Syy --noconfirm
bash "$repo_root/ci/check-repository-order.sh" /etc/pacman.conf "$channel" >/dev/null
