#!/usr/bin/env bash
# Run inside an unprivileged Arch build job with no signing/R2 credentials.
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
manifest="$(realpath -e -- "${1:?manifest path is required}")"
output="$(realpath -m -- "${2:?output directory is required}")"
channel="${3:-stable}"
candidate="${4:-}"
case "$channel" in
  stable) ;;
  beta)
    case "$candidate" in meoui-qml|meo-icons|meo-desktop|meo-account|meo-settings|omnistore-bin) ;; *)
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

python3 "$repo_root/scripts/validate_manifest.py" "$manifest"
python3 "$repo_root/scripts/verify_manifest_sources.py" "$manifest"
python3 "$repo_root/scripts/validate_keyring_payload.py" "$repo_root/packages/meo-keyring/files"

build_context() {
  local package="$1"
  local context="$2"
  shift 2
  (
    cd "$context"
    makepkg --config "$output/makepkg.conf" --syncdeps --noconfirm --needed "$@"
  )
  local built=()
  while IFS= read -r package_file; do built+=("$package_file"); done < <(
    cd "$context"
    makepkg --config "$output/makepkg.conf" --packagelist
  )
  [ "${#built[@]}" -gt 0 ] || { echo "No package produced for $package" >&2; exit 3; }
  for package_file in "${built[@]}"; do
    [ -f "$package_file" ] || { echo "Expected package output is missing: $package_file" >&2; exit 3; }
    cp -- "$package_file" "$output/packages/"
  done
}

if [ "$channel" = stable ]; then
  core_output="$(python3 - "$manifest" <<'PY'
import json, sys
manifest = json.load(open(sys.argv[1]))
order = ('meoui-qml', 'meo-icons', 'meo-desktop', 'meo-account', 'meo-settings', 'omnistore-bin')
print(*(name for name in order if name in manifest['components']), sep='\n')
PY
)"
  mapfile -t core_packages <<<"$core_output"
else
  core_packages=("$candidate")
fi
for package in "${core_packages[@]}"; do
  context="$output/contexts/$package"
  python3 "$repo_root/scripts/stage_component.py" "$manifest" "$package" "$context"
  build_context "$package" "$context" --noextract
  # Build jobs have no release secrets. Installing their own unsigned outputs
  # is confined to this disposable builder and only enables downstream builds.
  sudo pacman -U --noconfirm "$output/packages/$package-"*.pkg.tar.*
done

if [ "$channel" = stable ]; then
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
    build_context "$package" "$context"
    if [ "$package" != meo-channel-beta ]; then
      sudo pacman -U --noconfirm "$output/packages/$package-"*.pkg.tar.*
    fi
  done
fi

artifact_arguments=(create --manifest "$manifest" --packages "$output/packages"
  --output "$output/artifacts.json" --channel "$channel")
[ "$channel" = beta ] && artifact_arguments+=(--candidate "$candidate")
python3 "$repo_root/scripts/artifact_manifest.py" "${artifact_arguments[@]}"
python3 "$repo_root/scripts/artifact_manifest.py" verify \
  --contract "$output/artifacts.json" --manifest "$manifest" --packages "$output/packages"
