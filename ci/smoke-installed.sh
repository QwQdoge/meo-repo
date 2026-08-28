#!/usr/bin/env bash
# Stable train smoke after all packages have been installed in the disposable
# build container. No network refresh or privilege credentials are used here.
set -euo pipefail

for package in meoui-qml meo-icons meo-desktop meo-account meo-settings omnistore-bin \
               meo-keyring meo-mirrorlist meo-channel-stable meo-release \
               meo-core-meta meo-apps-meta meo-recommended-meta; do
  pacman -Q "$package" >/dev/null
done
pacman -Qlq meoui-qml | grep -q '/MeoUI/qmldir$'
pacman -Qlq meo-icons | grep -q '/icons/MeoSymbols/index.theme$'
pacman -Qlq meo-desktop | grep -Eq '/(wayland-sessions|xsessions|plasma/look-and-feel)/'
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
