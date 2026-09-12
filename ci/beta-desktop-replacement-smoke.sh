#!/usr/bin/env bash
# Prove that a Beta user's normal sysupgrade replaces the legacy runtime with
# the unsigned meo-desktop candidate before that candidate can be signed.
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
manifest="$(realpath -e -- "${1:?reviewed manifest is required}")"
artifact_dir="$(realpath -e -- "${2:?artifact directory is required}")"
package_dir="$artifact_dir/packages"
[ -d "$package_dir" ] || { echo "Candidate package directory is missing" >&2; exit 2; }

candidate_package=("$package_dir"/meo-desktop-*.pkg.tar.zst)
[ "${#candidate_package[@]}" -eq 1 ] && [ -f "${candidate_package[0]}" ] || {
  echo "Beta desktop replacement smoke requires exactly one meo-desktop package" >&2
  exit 2
}
candidate_version="$(bsdtar -xOf "${candidate_package[0]}" .PKGINFO | awk '$1 == "pkgver" && $2 == "=" {print $3; exit}')"
[ -n "$candidate_version" ] || { echo "Candidate package has no pkgver" >&2; exit 2; }

for command_name in pacman pacman-key repo-add bsdtar stat systemd-tmpfiles python3; do
  command -v "$command_name" >/dev/null || { echo "Required replacement-smoke command is missing: $command_name" >&2; exit 2; }
done

work_dir="$(mktemp -d)"
test_root="$work_dir/root"
candidate_repo="$work_dir/candidate"
trap 'rm -rf -- "$work_dir"' EXIT
install -d "$test_root/etc/pacman.d/gnupg" "$test_root/var/lib/pacman" \
  "$test_root/var/cache/pacman/pkg" "$test_root/var/log" "$candidate_repo"

cp -- "${candidate_package[0]}" "$candidate_repo/"
repo-add "$candidate_repo/meo-candidate.db.tar.gz" "$candidate_repo"/*.pkg.tar.zst >/dev/null

write_config() {
  local path="$1"
  local include_candidate="$2"
  cat >"$path" <<EOF
[options]
Architecture = auto
SigLevel = Required DatabaseOptional
LocalFileSigLevel = Optional
ParallelDownloads = 5
GPGDir = $test_root/etc/pacman.d/gnupg
EOF
  cat >>"$path" <<'EOF'

[core]
Server = https://geo.mirror.pkgbuild.com/$repo/os/$arch

[extra]
Server = https://geo.mirror.pkgbuild.com/$repo/os/$arch
EOF
  if [ "$include_candidate" = 1 ]; then
    cat >>"$path" <<EOF

[meo-candidate]
SigLevel = Never
Server = file://$candidate_repo
EOF
  fi
  cat >>"$path" <<'EOF'

[meo-beta]
SigLevel = Required TrustedOnly
Server = https://packages.meoarch.org/meo-beta/os/x86_64

[meo]
SigLevel = Required TrustedOnly
Server = https://packages.meoarch.org/meo/os/x86_64
EOF
}

previous_config="$work_dir/previous.conf"
candidate_config="$work_dir/candidate.conf"
write_config "$previous_config" 0
write_config "$candidate_config" 1

pacman-key --gpgdir "$test_root/etc/pacman.d/gnupg" --init
pacman-key --gpgdir "$test_root/etc/pacman.d/gnupg" --populate archlinux
pacman-key --gpgdir "$test_root/etc/pacman.d/gnupg" \
  --populate-from "$repo_root/packages/meo-keyring/files" --populate meo

# Reproduce the currently deployed Beta host shape: Settings pulls in the
# standalone runtime, while meo-desktop is not installed yet.
pacman --root "$test_root" --config "$previous_config" -Syu --needed --noconfirm \
  base python meo/meo-keyring meo/meo-mirrorlist meo/meo-channel-beta \
  meo/meo-release meo-settings
pacman --root "$test_root" -Q meo-kde-runtime >/dev/null
! pacman --root "$test_root" -Q meo-desktop >/dev/null 2>&1

pacman --root "$test_root" --config "$candidate_config" -Syu --noconfirm

test "$(pacman --root "$test_root" -Q meo-desktop | awk '{print $2}')" = "$candidate_version"
! pacman --root "$test_root" -Q meo-kde-runtime >/dev/null 2>&1
pacman --root "$test_root" -Q meo-channel-beta >/dev/null
for directory in / /etc /usr /var; do
  test "$(stat -c '%u:%g' "$test_root$directory")" = 0:0 || {
    echo "Beta desktop replacement left unsafe ownership on $directory" >&2
    exit 3
  }
done
systemd-tmpfiles --root="$test_root" --create --remove
test -s "$test_root/usr/lib/qt6/qml/MeoKDE/qmldir"
test -s "$test_root/usr/share/plasma/plasmoids/org.meo.topbar/metadata.json"
python3 "$repo_root/scripts/validate_manifest.py" "$manifest" >/dev/null
echo "PASS: public Beta runtime replaced by meo-desktop through pacman -Syu"
