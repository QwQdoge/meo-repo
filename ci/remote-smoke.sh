#!/usr/bin/env bash
# Disposable Arch runner smoke test against packages.meoarch.org.
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
channel="${1:?stable or beta is required}"
candidate="${2:-}"
manifest="${3:?reviewed manifest is required}"
python3 "$repo_root/scripts/validate_manifest.py" "$manifest" --channel "$channel"
temporary_keyring_paths=()
cleanup_keyring_bootstrap() {
  local path
  for path in "${temporary_keyring_paths[@]}"; do
    rm -f -- "$path"
  done
  temporary_keyring_paths=()
}
for file in meo.gpg meo-trusted meo-revoked; do
  source_file="$repo_root/packages/meo-keyring/files/$file"
  destination="/usr/share/pacman/keyrings/$file"
  [ -s "$source_file" ] || { echo "Missing public keyring file: $file" >&2; exit 2; }
  if [ -e "$destination" ] || [ -L "$destination" ]; then
    echo "Refusing pre-existing Meo keyring bootstrap path: $destination" >&2
    exit 2
  fi
done
trap 'cleanup_keyring_bootstrap' EXIT
for file in meo.gpg meo-trusted meo-revoked; do
  destination="/usr/share/pacman/keyrings/$file"
  install -Dm644 "$repo_root/packages/meo-keyring/files/$file" "$destination"
  temporary_keyring_paths+=("$destination")
done
pacman-key --init
pacman-key --populate archlinux meo
# The package transaction below installs meo-keyring and must own these paths.
cleanup_keyring_bootstrap

config="$(mktemp)"
trap 'cleanup_keyring_bootstrap; rm -f -- "$config"' EXIT
cp -- /etc/pacman.conf "$config"
case "$channel" in
  stable)
    repositories=$'[meo]\nSigLevel = Required TrustedOnly\nServer = https://packages.meoarch.org/meo/os/x86_64'
    if [ -n "$candidate" ]; then
      # A sparse publication updates one artifact, but acceptance still
      # installs the Stable core meta package so the complete supported
      # package graph and installed-payload smoke are exercised.
      packages=("$candidate" "meo/meo-core-meta")
    else
      package_output="$(PYTHONPATH="$repo_root/scripts" python3 - "$manifest" <<'PY'
import json,sys
from artifact_manifest import control_packages
manifest=json.load(open(sys.argv[1], encoding="utf-8"))
print(*manifest['components'], *(name for name in control_packages(manifest) if name != 'meo-channel-beta'), sep="\n")
PY
      )"
      mapfile -t packages <<<"$package_output"
    fi
    channel_package=meo-channel-stable
    ;;
  beta)
    case "$candidate" in all|meoui-qml|meo-icons|meo-plasma-login-manager|meo-desktop|meo-kde-runtime|meo-account|meo-icon-studio|meo-settings|omnistore-bin|meo-ai|meo-repair) ;; *) echo "Invalid beta candidate" >&2; exit 2;; esac
    repositories=$'[meo-beta]\nSigLevel = Required TrustedOnly\nServer = https://packages.meoarch.org/meo-beta/os/x86_64\n\n[meo]\nSigLevel = Required TrustedOnly\nServer = https://packages.meoarch.org/meo/os/x86_64'
    packages=("$candidate")
    if [ "$candidate" = all ]; then
      # Desktop provides the standalone runtime; installing both explicitly
      # would conflict. Verify the standalone variant in its candidate run.
      mapfile -t packages < <(python3 - "$manifest" <<'PY'
import json, sys
components = json.load(open(sys.argv[1], encoding="utf-8"))["components"]
print(*(name for name in components if name != "meo-kde-runtime"
        or "meo-desktop" not in components), sep="\n")
PY
      )
    fi
    channel_package=meo-channel-beta
    ;;
  *) echo "Invalid channel" >&2; exit 2 ;;
esac
printf '\n%s\n' "$repositories" >>"$config"
pacman --config "$config" -Syu --needed --noconfirm \
  meo/meo-keyring meo/meo-mirrorlist "meo/$channel_package" meo/meo-release "${packages[@]}"
bash "$repo_root/ci/check-repository-order.sh" "$config" "$channel"
if [ "$channel" = beta ]; then
  ! pacman --config "$config" -Si meo-beta/meo-release >/dev/null 2>&1 || {
    echo "Beta overlay must not duplicate the Stable control package meo-release" >&2; exit 3;
  }
  pacman --config "$config" -Si meo/meo-release >/dev/null || {
    echo "Stable fallback does not provide meo-release" >&2; exit 3;
  }
fi
# Verify the installed, package-owned channel configuration too, not only
# the temporary bootstrap configuration used for the first transaction.
test -s /etc/pacman.d/meo-channel.conf
printf '\nInclude = /etc/pacman.d/meo-channel.conf\n' >>/etc/pacman.conf
bash "$repo_root/ci/check-repository-order.sh" /etc/pacman.conf "$channel"
pacman -Syu --noconfirm
if [ "$channel" = beta ]; then
  # Installation alone can accidentally accept the previous public version.
  for package in "${packages[@]}"; do
    expected="$(python3 - "$manifest" "$package" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["components"][sys.argv[2]]["expectedVersion"])
PY
    )"
    actual="$(pacman -Q "$package")"
    [ "$actual" = "$package $expected" ] || {
      echo "Published version mismatch: expected $package $expected, got $actual" >&2
      exit 3
    }
  done
fi
for directory in / /etc /usr /var; do
  test "$(stat -c '%u:%g' "$directory")" = 0:0 || {
    echo "Remote installation left unsafe ownership on $directory" >&2
    exit 3
  }
done
systemd-tmpfiles --create --remove
if [ "$candidate" = meo-settings ] || [ "$candidate" = all ]; then
  stale_qml_root="$(mktemp -d)"
  trap 'cleanup_keyring_bootstrap; rm -f -- "$config"; rm -rf -- "$stale_qml_root"' EXIT
  mkdir -p "$stale_qml_root/MeoUI"
  printf 'module MeoUI\n' >"$stale_qml_root/MeoUI/qmldir"
  QML_IMPORT_PATH="$stale_qml_root" QML2_IMPORT_PATH="$stale_qml_root" \
    QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_FORCE_STDERR_LOGGING=1 \
    timeout 120 meo-settings --smoke
  QML_IMPORT_PATH="$stale_qml_root" QML2_IMPORT_PATH="$stale_qml_root" \
    QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_FORCE_STDERR_LOGGING=1 \
    timeout 30 meo-welcome --show --smoke
fi
if [ "$candidate" = meo-ai ] || [ "$candidate" = all ]; then
  QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software timeout 30 meo-ai --smoke
  MEO_AI_BACKEND_FACTORY= timeout 30 meo-agent-service --self-check
  # The real compatibility engine must initialize without a display/provider.
  timeout 60 dbus-run-session -- meo-agent-service --self-check
fi
if [ "$candidate" = meo-repair ] || [ "$candidate" = all ]; then
  timeout 30 meoarch-repair --list-categories
  QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software timeout 30 \
    meoarch-repair --preview --screenshot /tmp/meo-repair-preview.png
fi
if [ "$candidate" = omnistore-bin ] || [ "$candidate" = all ]; then
  QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software timeout 30 omnistore --check-qml
fi
[ "$channel" != stable ] || "$repo_root/ci/smoke-installed.sh" "$manifest"
