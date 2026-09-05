#!/usr/bin/env bash
# Stable train smoke after all packages have been installed in the disposable
# build container. No network refresh or privilege credentials are used here.
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
manifest="${1:?reviewed manifest is required}"
package_output="$(PYTHONPATH="$repo_root/scripts" python3 - "$manifest" <<'PY'
import json, sys
from artifact_manifest import control_packages
manifest = json.load(open(sys.argv[1]))
print(*manifest['components'], *(name for name in control_packages(manifest) if name != 'meo-channel-beta'), sep='\n')
PY
)"
mapfile -t packages <<<"$package_output"
for package in "${packages[@]}"; do
  pacman -Q "$package" >/dev/null
done
# Consume the complete listing: grep -q can close a large package listing
# early, giving pacman SIGPIPE and a false failure under pipefail.
pacman -Qlq meoui-qml | grep '/MeoUI/qmldir$' >/dev/null
pacman -Qlq meo-icons | grep '/icons/MeoSymbols/index.theme$' >/dev/null
pacman -Qlq meo-desktop | grep -E '/(wayland-sessions|xsessions|plasma/look-and-feel)/' >/dev/null
for path in /usr/bin/meo-dock /usr/lib/qt6/qml/MeoKDE/qmldir \
  /usr/lib/qt6/qml/Meo/System/libmeosystemplugin.so /etc/xdg/autostart/org.meo.dock.desktop \
  /usr/share/plasma/plasmoids/org.meo.topbar/metadata.json /usr/share/meo-release/application-catalog.json; do
  test -s "$path"
done
profile="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("profile", "recommended"))' "$manifest")"
[ "$profile" != minimal ] || { echo "PASS: installed minimal Meo package payload"; exit 0; }
command -v meo-settings >/dev/null
command -v meo-accountd >/dev/null
command -v meo-account-auth-dialog >/dev/null
test -s /usr/share/dbus-1/interfaces/org.meo.Accounts1.xml
test -s /usr/share/meo-account/clients/org.meo.Settings.json
test -s /usr/share/meo-account/clients/org.meo.OmniStore.json
grep -q '^Exec=/usr/bin/omnistore %u$' /usr/share/applications/omnistore.desktop
grep -q '^MimeType=x-scheme-handler/omnistore;$' /usr/share/applications/omnistore.desktop
command -v omnistore >/dev/null
command -v omnistore-cli >/dev/null
command -v omnistore-apps-export >/dev/null
test -s /usr/share/meo-release/application-catalog.json
timeout 10 omnistore-cli --help | grep -q -- '--install'

export_snapshot="$(mktemp)"
trap 'rm -f -- "$export_snapshot"' EXIT
timeout 30 omnistore-apps-export >"$export_snapshot"
python3 - "$export_snapshot" <<'PY'
import json,sys
payload=json.load(open(sys.argv[1], encoding="utf-8"))
if not isinstance(payload, dict) or payload.get("status") not in {"success", "ok"}:
    raise SystemExit("OmniStore exporter smoke returned an invalid payload")
PY
