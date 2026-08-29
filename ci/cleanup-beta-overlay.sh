#!/usr/bin/env bash
# Protected stable-publication follow-up. Removes only beta DB entries which
# pacman's vercmp says are no newer than the just-published Stable entry.
set -euo pipefail
set +x

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
: "${MEO_SIGNING_KEY_FINGERPRINT:?protected signing fingerprint is required}"
: "${R2_ENDPOINT:?R2 endpoint is required}"
: "${R2_BUCKET:?R2 bucket is required}"
: "${CLOUDFLARE_ZONE_ID:?Cloudflare zone id is required}"
: "${CLOUDFLARE_API_TOKEN:?Cloudflare purge token is required}"
for command_name in aws curl gpg jq repo-remove vercmp; do
  command -v "$command_name" >/dev/null || { echo "Required command is missing: $command_name" >&2; exit 2; }
done

beta_key="meo-beta/os/x86_64/meo-beta.db.tar.gz"
beta_count="$(aws --endpoint-url "$R2_ENDPOINT" s3api list-objects-v2 --bucket "$R2_BUCKET" \
  --prefix "$beta_key" --query "length(Contents[?Key=='$beta_key'])" --output text)"
[ "$beta_count" != 0 ] || { echo "No beta overlay exists; cleanup is not required"; exit 0; }

work_dir="$(mktemp -d)"
trap 'rm -rf -- "$work_dir"' EXIT
for repository in meo meo-beta; do
  for metadata in "$repository.db.tar.gz" "$repository.db.tar.gz.sig"; do
    aws --endpoint-url "$R2_ENDPOINT" s3 cp \
      "s3://$R2_BUCKET/$repository/os/x86_64/$metadata" "$work_dir/$metadata" --only-show-errors
  done
  gpg --batch --verify "$work_dir/$repository.db.tar.gz.sig" "$work_dir/$repository.db.tar.gz"
done
for metadata in meo-beta.files.tar.gz meo-beta.files.tar.gz.sig; do
  aws --endpoint-url "$R2_ENDPOINT" s3 cp \
    "s3://$R2_BUCKET/meo-beta/os/x86_64/$metadata" "$work_dir/$metadata" --only-show-errors
done
gpg --batch --verify "$work_dir/meo-beta.files.tar.gz.sig" "$work_dir/meo-beta.files.tar.gz"
rm -f -- "$work_dir/meo-beta.db.tar.gz.sig" "$work_dir/meo-beta.files.tar.gz.sig"

removal_output="$(python3 "$repo_root/scripts/overlay_cleanup.py" \
  "$work_dir/meo.db.tar.gz" "$work_dir/meo-beta.db.tar.gz")"
removals=()
while IFS= read -r package_name; do
  [ -n "$package_name" ] && removals+=("$package_name")
done <<<"$removal_output"
[ "${#removals[@]}" -gt 0 ] || { echo "No obsolete beta overlays found"; exit 0; }
repo-remove --sign --key "$MEO_SIGNING_KEY_FINGERPRINT" "$work_dir/meo-beta.db.tar.gz" "${removals[@]}"

for mutable in meo-beta.db.tar.gz meo-beta.files.tar.gz; do
  source_file="$work_dir/$mutable"
  alias_name="${mutable/.tar.gz/}"
  [ -s "$source_file" ] && [ -s "$source_file.sig" ] || { echo "Signed beta metadata is missing" >&2; exit 3; }
  for object_name in "$mutable" "$alias_name"; do
    aws --endpoint-url "$R2_ENDPOINT" s3 cp "$source_file" \
      "s3://$R2_BUCKET/meo-beta/os/x86_64/$object_name" \
      --cache-control 'no-cache,max-age=0,must-revalidate' --content-type application/octet-stream --only-show-errors
    aws --endpoint-url "$R2_ENDPOINT" s3 cp "$source_file.sig" \
      "s3://$R2_BUCKET/meo-beta/os/x86_64/$object_name.sig" \
      --cache-control 'no-cache,max-age=0,must-revalidate' --content-type application/pgp-signature --only-show-errors
  done
done

payload="$(jq -n '{files:[
  "https://packages.meoarch.org/meo-beta/os/x86_64/meo-beta.db",
  "https://packages.meoarch.org/meo-beta/os/x86_64/meo-beta.db.sig",
  "https://packages.meoarch.org/meo-beta/os/x86_64/meo-beta.db.tar.gz",
  "https://packages.meoarch.org/meo-beta/os/x86_64/meo-beta.db.tar.gz.sig",
  "https://packages.meoarch.org/meo-beta/os/x86_64/meo-beta.files",
  "https://packages.meoarch.org/meo-beta/os/x86_64/meo-beta.files.sig",
  "https://packages.meoarch.org/meo-beta/os/x86_64/meo-beta.files.tar.gz",
  "https://packages.meoarch.org/meo-beta/os/x86_64/meo-beta.files.tar.gz.sig"
]}')"
response="$work_dir/purge.json"
curl --fail --silent --show-error \
  "https://api.cloudflare.com/client/v4/zones/$CLOUDFLARE_ZONE_ID/purge_cache" \
  --header "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  --header 'Content-Type: application/json' --data "$payload" --output "$response"
jq -e '.success == true' "$response" >/dev/null

curl --fail --silent --show-error --location \
  'https://packages.meoarch.org/meo-beta/os/x86_64/meo-beta.db' \
  --output "$work_dir/remote-meo-beta.db"
curl --fail --silent --show-error --location \
  'https://packages.meoarch.org/meo-beta/os/x86_64/meo-beta.db.sig' \
  --output "$work_dir/remote-meo-beta.db.sig"
gpg --batch --verify "$work_dir/remote-meo-beta.db.sig" "$work_dir/remote-meo-beta.db"
echo "Removed obsolete beta overlays: ${removals[*]}"
