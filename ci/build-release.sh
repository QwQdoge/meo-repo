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

python3 "$repo_root/scripts/validate_manifest.py" "$manifest"
python3 "$repo_root/scripts/verify_manifest_sources.py" "$manifest"
python3 "$repo_root/scripts/validate_keyring_payload.py" "$repo_root/packages/meo-keyring/files"

build_context() {
  local package="$1"
  local context="$2"
  (
    cd "$context"
    makepkg --syncdeps --noconfirm --needed --noextract
  )
  local built=()
  while IFS= read -r package_file; do built+=("$package_file"); done < <(
    cd "$context"
    makepkg --packagelist
  )
  [ "${#built[@]}" -gt 0 ] || { echo "No package produced for $package" >&2; exit 3; }
  for package_file in "${built[@]}"; do
    [ -f "$package_file" ] || { echo "Expected package output is missing: $package_file" >&2; exit 3; }
    cp -- "$package_file" "$output/packages/"
  done
}

if [ "$channel" = stable ]; then
  core_packages=(meoui-qml meo-icons meo-desktop meo-account meo-settings omnistore-bin)
else
  core_packages=("$candidate")
fi
for package in "${core_packages[@]}"; do
  context="$output/contexts/$package"
  python3 "$repo_root/scripts/stage_component.py" "$manifest" "$package" "$context"
  build_context "$package" "$context"
  # Build jobs have no release secrets. Installing their own unsigned outputs
  # is confined to this disposable builder and only enables downstream builds.
  sudo pacman -U --noconfirm "$output/packages/$package-"*.pkg.tar.*
done

if [ "$channel" = stable ]; then
  for package in meo-keyring meo-mirrorlist meo-channel-stable meo-channel-beta meo-release \
                 meo-core-meta meo-apps-meta meo-recommended-meta; do
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
