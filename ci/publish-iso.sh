#!/usr/bin/env bash
# Publishes the newest Live ISO to the Cloudflare R2 mirror and keeps only that one.
# Run by the owner (or a protected environment) with R2 credentials; never in an
# unprotected job. The new ISO is uploaded and verified before older ones are removed,
# so the mirror always holds at least one working ISO.
#
#   R2_ENDPOINT=https://<account>.r2.cloudflarestorage.com \
#   AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... ci/publish-iso.sh path/to/meoarch-os-*.iso
set -euo pipefail
set +x

iso="$(realpath -e -- "${1:?path to the ISO is required}")"
name="$(basename -- "$iso")"
case "$name" in meoarch-os-*-x86_64.iso) ;; *) echo "Unexpected ISO name: $name" >&2; exit 2 ;; esac
: "${R2_ENDPOINT:?R2 S3 endpoint is required}"
bucket="${R2_ISO_BUCKET:-meo-iso}"
export AWS_DEFAULT_REGION=auto
for command_name in aws jq sha256sum; do
  command -v "$command_name" >/dev/null || { echo "Required command is missing: $command_name" >&2; exit 2; }
done
s3() { aws --endpoint-url "$R2_ENDPOINT" "$@"; }

sha="$(sha256sum -- "$iso" | cut -d' ' -f1)"
if [ -f "$iso.sha256" ]; then
  recorded="$(cut -d' ' -f1 <"$iso.sha256")"
  [ "$recorded" = "$sha" ] || { echo "$iso.sha256 does not match the file" >&2; exit 1; }
fi
size="$(stat -c %s -- "$iso")"

work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
printf '%s  %s\n' "$sha" "$name" >"$work/$name.sha256"
jq -n --arg name "$name" --arg sha "$sha" --argjson size "$size" \
  '{name:$name, sha256:$sha, size:$size}' >"$work/latest.json"

s3 s3 cp "$iso" "s3://$bucket/$name" --no-progress
remote_size="$(s3 s3api head-object --bucket "$bucket" --key "$name" --query ContentLength --output text)"
[ "$remote_size" = "$size" ] || { echo "Uploaded size $remote_size differs from $size; older ISOs kept" >&2; exit 1; }
s3 s3 cp "$work/$name.sha256" "s3://$bucket/$name.sha256" --no-progress
s3 s3 cp "$work/latest.json" "s3://$bucket/latest.json" --no-progress --content-type application/json

# Only now drop every other ISO (and its checksum): exactly one stays.
s3 s3api list-objects-v2 --bucket "$bucket" --query 'Contents[].Key' --output json \
  | jq -r --arg keep "$name" '.[]? | select(test("^meoarch-os-.*-x86_64\\.iso(\\.sha256)?$")) | select(. != $keep and . != ($keep + ".sha256"))' \
  | while read -r old; do
      echo "Removing older object: $old"
      s3 s3api delete-object --bucket "$bucket" --key "$old"
    done
echo "Published $name ($size bytes, sha256 $sha)"
