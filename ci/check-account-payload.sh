#!/usr/bin/env bash
# Read-only Account package contract. An alternate root supports isolated tests.
set -euo pipefail
root="${1:-/}"
for executable in meo-accountd meo-account-auth-dialog; do
  test -x "$root/usr/bin/$executable"
done
service="$root/usr/lib/systemd/user/meo-accountd.service"
test -s "$service"
grep -q '^Type=dbus$' "$service"
grep -q '^BusName=org\.meo\.Accounts1$' "$service"
grep -q '^WantedBy=graphical-session\.target$' "$service"
link="$root/usr/lib/systemd/user/graphical-session.target.wants/meo-accountd.service"
test -L "$link"
[ "$(readlink "$link")" = '../meo-accountd.service' ]
activation="$root/usr/share/dbus-1/services/org.meo.Accounts1.service"
test -s "$activation"
grep -q '^Name=org\.meo\.Accounts1$' "$activation"
grep -q '^SystemdService=meo-accountd\.service$' "$activation"
test -s "$root/usr/share/dbus-1/interfaces/org.meo.Accounts1.xml"
config="$root/etc/meo-account/broker.conf"
test -s "$config"
grep -q '^BaseUrl=https://account\.meoarch\.org$' "$config"
grep -q '^ApiUrl=https://api\.meoarch\.org$' "$config"
grep -q '^ClientId=[^[:space:]]\+$' "$config"
grep -q '^RedirectUri=http://127\.0\.0\.1:43887/callback$' "$config"
if grep -q '^SupabaseUrl=' "$config"; then
  echo 'Retired Supabase broker configuration is not accepted.' >&2
  exit 1
fi
echo 'PASS: Account broker activation and public Meo API configuration'
