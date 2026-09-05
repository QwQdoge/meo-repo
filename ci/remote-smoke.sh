#!/usr/bin/env bash
# Disposable Arch runner smoke test against packages.meoarch.org.
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
channel="${1:?stable or beta is required}"
candidate="${2:-}"
manifest="${3:?reviewed manifest is required}"
for file in meo.gpg meo-trusted meo-revoked; do
  [ -s "$repo_root/packages/meo-keyring/files/$file" ] || { echo "Missing public keyring file: $file" >&2; exit 2; }
done
pacman-key --init
pacman-key --populate archlinux
pacman-key --populate-from "$repo_root/packages/meo-keyring/files" --populate meo

config="$(mktemp)"
trap 'rm -f -- "$config"' EXIT
cp -- /etc/pacman.conf "$config"
case "$channel" in
  stable)
    repositories=$'[meo]\nSigLevel = Required TrustedOnly\nServer = https://packages.meoarch.org/meo/os/x86_64'
    package_output="$(PYTHONPATH="$repo_root/scripts" python3 - "$manifest" <<'PY'
import json,sys
from artifact_manifest import control_packages
manifest=json.load(open(sys.argv[1], encoding="utf-8"))
print(*manifest['components'], *(name for name in control_packages(manifest) if name != 'meo-channel-beta'), sep="\n")
PY
)"
    mapfile -t packages <<<"$package_output"
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
bash "$repo_root/ci/check-repository-order.sh" "$config" "$channel"
if [ "$channel" = beta ]; then
  ! pacman --config "$config" -Si meo-beta/meo-release >/dev/null 2>&1 || {
    echo "Beta overlay must not duplicate the Stable control package meo-release" >&2; exit 3;
  }
  pacman --config "$config" -Si meo/meo-release >/dev/null || {
    echo "Stable fallback does not provide meo-release" >&2; exit 3;
  }
fi
pacman --config "$config" -S --needed --noconfirm \
  meo/meo-keyring meo/meo-mirrorlist "meo/$channel_package" meo/meo-release "${packages[@]}"
# Verify the installed, package-owned channel configuration too, not only
# the temporary bootstrap configuration used for the first transaction.
test -s /etc/pacman.d/meo-channel.conf
printf '\nInclude = /etc/pacman.d/meo-channel.conf\n' >>/etc/pacman.conf
bash "$repo_root/ci/check-repository-order.sh" /etc/pacman.conf "$channel"
pacman -Sy --noconfirm
[ "$channel" != stable ] || "$repo_root/ci/smoke-installed.sh" "$manifest"
