#!/usr/bin/env bash
# Run inside an unprivileged Arch build job with no signing/R2 credentials.
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
manifest="$(realpath -e -- "${1:?manifest path is required}")"
output="$(realpath -m -- "${2:?output directory is required}")"
channel="${3:-stable}"
candidate="${4:-}"
case "$channel" in
  stable)
    case "$candidate" in ''|meoui-qml|meo-icons|meo-plasma-login-manager|meo-desktop|meo-kde-runtime|meo-account|meo-icon-studio|meo-settings|omnistore-bin|meo-ai|meo-repair) ;; *)
      echo "Invalid Stable candidate" >&2; exit 2;;
    esac
    ;;
  beta)
    case "$candidate" in meoui-qml|meo-icons|meo-plasma-login-manager|meo-desktop|meo-kde-runtime|meo-account|meo-icon-studio|meo-settings|omnistore-bin|meo-ai|meo-repair) ;; *)
      echo "Beta build requires one reviewed core package candidate" >&2; exit 2;;
    esac
    ;;
  *) echo "Invalid channel" >&2; exit 2 ;;
esac
[ ! -e "$output" ] || { echo "Refusing to overwrite output directory: $output" >&2; exit 2; }
mkdir -p "$output/contexts" "$output/packages"
# Keep makepkg and --packagelist on the same explicit train policy. Arch's
# default debug option can list a debug split even for data-only packages,
# while the signed release contract intentionally contains only named inputs.
cp -- /etc/makepkg.conf "$output/makepkg.conf"
printf '\nOPTIONS+=(\x27!debug\x27)\n' >>"$output/makepkg.conf"

python3 "$repo_root/scripts/validate_manifest.py" "$manifest" --channel "$channel"
closure_args=("$manifest")
[ -n "$candidate" ] && closure_args+=(--candidate "$candidate")
python3 "$repo_root/scripts/validate_release_closure.py" "${closure_args[@]}"
if [ -n "$candidate" ]; then
  # A sparse candidate run verifies the immutable source it actually consumes.
  # This keeps unrelated private components from weakening or blocking a
  # public candidate build; each candidate is verified by its own run.
  python3 "$repo_root/scripts/verify_manifest_sources.py" "$manifest" --component "$candidate"
else
  python3 "$repo_root/scripts/verify_manifest_sources.py" "$manifest"
fi
python3 "$repo_root/scripts/validate_keyring_payload.py" "$repo_root/packages/meo-keyring/files"

source_date_epoch=""

component_source_date_epoch() {
  python3 - "$manifest" "$1" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
component = manifest["components"][sys.argv[2]]
epoch = component.get("sourceDateEpoch")
if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch <= 0:
    raise SystemExit(f"{sys.argv[2]} requires a positive sourceDateEpoch")
print(epoch)
PY
}

run_makepkg() {
  if [ -n "$source_date_epoch" ]; then
    SOURCE_DATE_EPOCH="$source_date_epoch" makepkg "$@"
  else
    makepkg "$@"
  fi
}

build_context() {
  local package="$1"
  local context="$2"
  shift 2
  (
    cd "$context"
    run_makepkg --config "$output/makepkg.conf" --syncdeps --noconfirm --needed "$@"
  )
  local built=()
  while IFS= read -r package_file; do built+=("$package_file"); done < <(
    cd "$context"
    run_makepkg --config "$output/makepkg.conf" --packagelist
  )
  [ "${#built[@]}" -gt 0 ] || { echo "No package produced for $package" >&2; exit 3; }
  for package_file in "${built[@]}"; do
    [ -f "$package_file" ] || { echo "Expected package output is missing: $package_file" >&2; exit 3; }
    cp -- "$package_file" "$output/packages/"
  done
}


control_package_filename() {
  local context="$1"
  local files=()
  while IFS= read -r package_file; do files+=("$package_file"); done < <(
    cd "$context"
    run_makepkg --config "$output/makepkg.conf" --packagelist
  )
  [ "${#files[@]}" -eq 1 ] || {
    echo "Control package must produce exactly one package file: $context" >&2
    return 3
  }
  basename -- "${files[0]}"
}

reuse_or_build_control() {
  local package="$1"
  local context="$2"
  local filename remote_url local_package local_signature http_code expected_version actual_identity

  filename="$(control_package_filename "$context")"
  remote_url="https://packages.meoarch.org/meo/os/x86_64/$filename"
  local_package="$reused_control_dir/$filename"
  local_signature="$local_package.sig"

  if ! http_code="$(curl --silent --show-error --location       --output "$local_package" --write-out '%{http_code}' "$remote_url")"; then
    echo "Failed to check the existing signed control package: $filename" >&2
    return 4
  fi

  case "$http_code" in
    200)
      curl --fail --silent --show-error --location         "$remote_url.sig" --output "$local_signature" || {
          echo "Existing control package is missing a valid detached signature: $filename" >&2
          return 4
        }
      GNUPGHOME="$control_verify_home" gpg --batch --verify         "$local_signature" "$local_package" >/dev/null 2>&1 || {
          echo "Existing control package signature verification failed: $filename" >&2
          return 4
        }
      expected_version="$(PYTHONPATH="$repo_root/scripts" python3 - "$package" <<'PY'
import sys
from artifact_manifest import literal_recipe_version
print(literal_recipe_version(sys.argv[1]))
PY
)"
      actual_identity="$(LC_ALL=C pacman -Qp "$local_package")"
      [ "$actual_identity" = "$package $expected_version" ] || {
        echo "Existing control package identity does not match its reviewed recipe: $filename" >&2
        return 4
      }
      cp -- "$local_package" "$output/packages/"
      echo "Reusing already-published signed control package: $filename"
      ;;
    404)
      rm -f -- "$local_package" "$local_signature"
      build_context "$package" "$context"
      ;;
    *)
      echo "Unexpected HTTP status while checking control package $filename: $http_code" >&2
      return 4
      ;;
  esac
}

if [ -n "$candidate" ]; then
  core_packages=("$candidate")
elif [ "$channel" = stable ]; then
  mapfile -t core_packages < <(
    python3 "$repo_root/scripts/validate_release_closure.py"       "$manifest" --print-build-order
  )
  [ "${#core_packages[@]}" -gt 0 ] || {
    echo "Stable package closure produced no buildable components" >&2
    exit 3
  }
fi
for package in "${core_packages[@]}"; do
  source_date_epoch="$(component_source_date_epoch "$package")"
  context="$output/contexts/$package"
  python3 "$repo_root/scripts/stage_component.py" "$manifest" "$package" "$context"
  build_context "$package" "$context" --noextract
  # Build jobs have no release secrets. Installing their own unsigned outputs
  # is confined to this disposable builder and only enables downstream builds.
  sudo pacman -U --noconfirm "$output/packages/$package-"*.pkg.tar.*
  if [ "$package" = meo-ai ]; then
    QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software timeout 30 meo-ai --smoke
    MEO_AI_BACKEND_FACTORY= timeout 30 meo-agent-service --self-check
    timeout 60 dbus-run-session -- meo-agent-service --self-check
  elif [ "$package" = meo-repair ]; then
    timeout 30 meoarch-repair --list-categories
  fi
done

if [ "$channel" = stable ] && [ -z "$candidate" ]; then
  # Control packages are either reused byte-for-byte from the signed Stable
  # repository or built from their own static recipes. Never leak the final
  # core component's deterministic timestamp into those package builds.
  source_date_epoch=""
  control_verify_home="$output/control-verify-gnupg"
  reused_control_dir="$output/reused-controls"
  install -d -m700 "$control_verify_home" "$reused_control_dir"
  GNUPGHOME="$control_verify_home" gpg --batch --import "$repo_root/packages/meo-keyring/files/meo.gpg" >/dev/null 2>&1

  control_output="$(PYTHONPATH="$repo_root/scripts" python3 - "$manifest" <<'PY'
import json, sys
from artifact_manifest import control_packages
print(*control_packages(json.load(open(sys.argv[1]))), sep='\n')
PY
)"
  mapfile -t controls <<<"$control_output"
  for package in "${controls[@]}"; do
    context="$output/contexts/$package"
    cp -a -- "$repo_root/packages/$package" "$context"
    if [ "$package" = meo-keyring ]; then
      python3 "$repo_root/scripts/render_keyring_recipe.py" "$context"
    fi
    reuse_or_build_control "$package" "$context"
    if [ "$package" != meo-channel-beta ]; then
      sudo pacman -U --noconfirm "$output/packages/$package-"*.pkg.tar.*
    fi
  done
fi

artifact_arguments=(create --manifest "$manifest" --packages "$output/packages"
  --output "$output/artifacts.json" --channel "$channel")
[ -n "$candidate" ] && artifact_arguments+=(--candidate "$candidate")
python3 "$repo_root/scripts/artifact_manifest.py" "${artifact_arguments[@]}"
python3 "$repo_root/scripts/artifact_manifest.py" verify \
  --contract "$output/artifacts.json" --manifest "$manifest" --packages "$output/packages"
