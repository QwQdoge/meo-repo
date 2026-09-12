#!/usr/bin/env bash
# Reproduce the supported update path before signing: install the previous
# public Beta/Stable state, switch to the unsigned candidate repository, then
# perform one full pacman -Syu transaction and run migration/runtime checks.
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
manifest="$(realpath -e -- "${1:?reviewed manifest is required}")"
artifact_dir="$(realpath -e -- "${2:?artifact directory is required}")"
package_dir="$artifact_dir/packages"
[ -d "$package_dir" ] || { echo "Candidate package directory is missing" >&2; exit 2; }

for command_name in pacman pacman-key repo-add chroot stat systemd-tmpfiles bsdtar sha256sum; do
  command -v "$command_name" >/dev/null || { echo "Required upgrade-smoke command is missing: $command_name" >&2; exit 2; }
done

work_dir="$(mktemp -d)"
test_root="$work_dir/root"
candidate_repo="$work_dir/candidate"
trap 'rm -rf -- "$work_dir"' EXIT
install -d "$test_root/etc/pacman.d/gnupg" "$test_root/var/lib/pacman" \
  "$test_root/var/cache/pacman/pkg" "$test_root/var/log" \
  "$test_root/scripts" "$candidate_repo"

cp -- "$package_dir"/*.pkg.tar.zst "$candidate_repo/"
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

# Beta 4 is the newest public pre-candidate state and installs the legacy
# meo-kde-runtime dependency that meo-desktop must replace during sysupgrade.
pacman --root "$test_root" --config "$previous_config" -Syu --needed --noconfirm \
  base python meo/meo-keyring meo/meo-mirrorlist meo/meo-channel-beta \
  meo/meo-release meo/meo-core-meta meo-settings
pacman --root "$test_root" -Q meo-kde-runtime >/dev/null
pacman --root "$test_root" -Q meo-release | grep -F '2026.08-2' >/dev/null

desktop_candidate=("$package_dir"/meo-desktop-*.pkg.tar.zst)
[ "${#desktop_candidate[@]}" -eq 1 ] && [ -f "${desktop_candidate[0]}" ] || {
  echo "Stable upgrade smoke requires exactly one meo-desktop package" >&2
  exit 2
}
decoration_plugin=usr/lib/qt6/plugins/org.kde.kdecoration3/org.meo.decoration.so
candidate_decoration_sha256="$(bsdtar -xOf "${desktop_candidate[0]}" "$decoration_plugin" | sha256sum | awk '{print $1}')"
# Match legacy source installs that left this path outside pacman's database.
install -Dm755 /bin/true "$test_root/$decoration_plugin"
! pacman --root "$test_root" -Qo "/$decoration_plugin" >/dev/null 2>&1

# Reproduce the legacy defect without touching any contents below the two
# affected top-level directories.
chown 1000:1000 "$test_root/etc" "$test_root/usr"
test "$(stat -c '%u:%g' "$test_root/etc")" = 1000:1000
test "$(stat -c '%u:%g' "$test_root/usr")" = 1000:1000

pacman --root "$test_root" --config "$candidate_config" -Syu --noconfirm

for directory in / /etc /usr /var; do
  test "$(stat -c '%u:%g' "$test_root$directory")" = 0:0 || {
    echo "Candidate upgrade left unsafe ownership on $directory" >&2
    exit 3
  }
done
pacman --root "$test_root" -Q meo-desktop >/dev/null
! pacman --root "$test_root" -Q meo-kde-runtime >/dev/null 2>&1
test "$(sha256sum "$test_root/$decoration_plugin" | awk '{print $1}')" = "$candidate_decoration_sha256"
desktop_check="$(pacman --root "$test_root" -Qkk meo-desktop)"
grep -F '0 altered files' <<<"$desktop_check" >/dev/null || {
  printf '%s\n' "$desktop_check" >&2
  exit 3
}

cp -- "$repo_root/ci/smoke-installed.sh" "$test_root/tmp/meo-smoke-installed.sh"
cp -- "$repo_root/scripts/artifact_manifest.py" "$test_root/scripts/artifact_manifest.py"
cp -- "$manifest" "$test_root/tmp/meo-release-manifest.json"
# The isolated pacman root intentionally has no mounted /proc or /sys. Apply
# tmpfiles to it through systemd-tmpfiles' supported offline-root interface;
# the remote smoke below exercises the normal live-root command separately.
systemd-tmpfiles --root="$test_root" --create --remove
chroot "$test_root" bash /tmp/meo-smoke-installed.sh \
  /tmp/meo-release-manifest.json meo-channel-beta
echo "PASS: previous public MeoArch state upgraded through pacman -Syu"
