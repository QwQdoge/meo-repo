#!/usr/bin/env bash
# Protected environment only. Verifies the unsigned build contract, signs
# packages and repo DBs, then publishes package objects before mutable DBs.
set -euo pipefail
set +x

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
manifest="$(realpath -e -- "${1:?manifest path is required}")"
artifact_dir="$(realpath -e -- "${2:?artifact directory is required}")"
channel="${3:?stable or beta channel is required}"
case "$channel" in stable) repository=meo ;; beta) repository=meo-beta ;; *) echo "Invalid channel" >&2; exit 2 ;; esac

: "${MEO_SIGNING_KEY_FINGERPRINT:?protected signing fingerprint is required}"
: "${R2_ENDPOINT:?R2 S3 endpoint is required}"
: "${R2_BUCKET:?R2 bucket is required}"
: "${CLOUDFLARE_ZONE_ID:?Cloudflare zone id is required}"
: "${CLOUDFLARE_API_TOKEN:?Cloudflare cache-purge API token is required}"
: "${MEO_PUBLICATION_PREFLIGHT_SHA256:?pre-signing artifact preflight digest is required}"
case "$MEO_PUBLICATION_PREFLIGHT_SHA256" in
  *[!0-9a-f]*|'') echo "Invalid publication preflight digest" >&2; exit 2 ;;
esac
[ "${#MEO_PUBLICATION_PREFLIGHT_SHA256}" -eq 64 ] || { echo "Invalid publication preflight digest" >&2; exit 2; }
for command_name in aws curl gpg jq repo-add; do
  command -v "$command_name" >/dev/null || { echo "Required command is missing: $command_name" >&2; exit 2; }
done

contract="$artifact_dir/artifacts.json"
packages="$artifact_dir/packages"
contract_sha256="$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$contract")"
[ "$contract_sha256" = "$MEO_PUBLICATION_PREFLIGHT_SHA256" ] || {
  echo "Artifact contract changed after the secret-free preflight" >&2; exit 3;
}
python3 "$repo_root/scripts/artifact_manifest.py" verify \
  --contract "$contract" --manifest "$manifest" --packages "$packages"
contract_channel="$(jq -r .channel "$contract")"
[ "$contract_channel" = "$channel" ] || { echo "Artifact channel does not match publication channel" >&2; exit 3; }

signing_key="$(gpg --batch --with-colons --list-secret-keys "$MEO_SIGNING_KEY_FINGERPRINT" | awk -F: '$1 == "sec" { print $5; exit }')"
[ -n "$signing_key" ] || { echo "Configured signing subkey is unavailable" >&2; exit 3; }

work_dir="$(mktemp -d)"
trap 'rm -rf -- "$work_dir"' EXIT
cp -- "$packages"/*.pkg.tar.* "$work_dir/"

if [ "$channel" = beta ]; then
  existing_key="$repository/os/x86_64/$repository.db.tar.gz"
  existing_count="$(aws --endpoint-url "$R2_ENDPOINT" s3api list-objects-v2 \
    --bucket "$R2_BUCKET" --prefix "$existing_key" --query 'length(Contents)' --output text)"
  if [ "$existing_count" != 0 ]; then
    for metadata in "$repository.db.tar.gz" "$repository.db.tar.gz.sig" \
                    "$repository.files.tar.gz" "$repository.files.tar.gz.sig"; do
      aws --endpoint-url "$R2_ENDPOINT" s3 cp \
        "s3://$R2_BUCKET/$repository/os/x86_64/$metadata" "$work_dir/$metadata" --only-show-errors
    done
    gpg --batch --verify "$work_dir/$repository.db.tar.gz.sig" "$work_dir/$repository.db.tar.gz"
    gpg --batch --verify "$work_dir/$repository.files.tar.gz.sig" "$work_dir/$repository.files.tar.gz"
    rm -f -- "$work_dir/$repository.db.tar.gz.sig" "$work_dir/$repository.files.tar.gz.sig"
  elif [ "${ALLOW_INITIAL_BETA_REPOSITORY:-0}" != 1 ]; then
    echo "Beta repository does not exist; explicit ALLOW_INITIAL_BETA_REPOSITORY=1 is required" >&2
    exit 4
  fi
fi

package_files=()
for package in "$work_dir"/*.pkg.tar.*; do
  case "$package" in *.sig) continue ;; esac
  package_files+=("$package")
  filename="$(basename -- "$package")"
  object_key="$repository/os/x86_64/$filename"
  object="s3://$R2_BUCKET/$object_key"
  existing="$(aws --endpoint-url "$R2_ENDPOINT" s3api list-objects-v2 --bucket "$R2_BUCKET" \
    --prefix "$object_key" --query "length(Contents[?Key=='$object_key'])" --output text)"
  if [ "$existing" != 0 ]; then
    remote_package="$work_dir/remote-$filename"
    aws --endpoint-url "$R2_ENDPOINT" s3 cp "$object" "$remote_package" --only-show-errors
    cmp -- "$package" "$remote_package" || { echo "Immutable package object already exists with different content: $filename" >&2; exit 4; }
    aws --endpoint-url "$R2_ENDPOINT" s3 cp "$object.sig" "$remote_package.sig" --only-show-errors
    gpg --batch --verify "$remote_package.sig" "$remote_package"
    continue
  fi
  gpg --batch --yes --detach-sign --local-user "$MEO_SIGNING_KEY_FINGERPRINT" "$package"
  aws --endpoint-url "$R2_ENDPOINT" s3 cp "$package" "$object" \
    --cache-control 'public,max-age=31536000,immutable' --content-type application/octet-stream --only-show-errors
  aws --endpoint-url "$R2_ENDPOINT" s3 cp "$package.sig" "$object.sig" \
    --cache-control 'public,max-age=31536000,immutable' --content-type application/pgp-signature --only-show-errors
  aws --endpoint-url "$R2_ENDPOINT" s3api head-object \
    --bucket "$R2_BUCKET" --key "$object_key" >/dev/null
  aws --endpoint-url "$R2_ENDPOINT" s3api head-object \
    --bucket "$R2_BUCKET" --key "$object_key.sig" >/dev/null
done

database="$work_dir/$repository.db.tar.gz"
repo-add --sign --key "$MEO_SIGNING_KEY_FINGERPRINT" "$database" "${package_files[@]}"
for mutable in "$repository.db.tar.gz" "$repository.files.tar.gz"; do
  source_file="$work_dir/$mutable"
  [ -s "$source_file" ] && [ -s "$source_file.sig" ] || { echo "Signed repository metadata is missing: $mutable" >&2; exit 4; }
  alias_name="${mutable/.tar.gz/}"
  for object_name in "$mutable" "$alias_name"; do
    aws --endpoint-url "$R2_ENDPOINT" s3 cp "$source_file" \
      "s3://$R2_BUCKET/$repository/os/x86_64/$object_name" \
      --cache-control 'no-cache,max-age=0,must-revalidate' --content-type application/octet-stream --only-show-errors
    aws --endpoint-url "$R2_ENDPOINT" s3 cp "$source_file.sig" \
      "s3://$R2_BUCKET/$repository/os/x86_64/$object_name.sig" \
      --cache-control 'no-cache,max-age=0,must-revalidate' --content-type application/pgp-signature --only-show-errors
  done
done

purge_payload="$(jq -n --arg base "https://packages.meoarch.org/$repository/os/x86_64" --arg repo "$repository" \
  '{files:[$base+"/"+$repo+".db",$base+"/"+$repo+".db.sig",$base+"/"+$repo+".db.tar.gz",$base+"/"+$repo+".db.tar.gz.sig",$base+"/"+$repo+".files",$base+"/"+$repo+".files.sig",$base+"/"+$repo+".files.tar.gz",$base+"/"+$repo+".files.tar.gz.sig"]}')"
purge_response="$work_dir/purge.json"
curl --fail --silent --show-error \
  "https://api.cloudflare.com/client/v4/zones/$CLOUDFLARE_ZONE_ID/purge_cache" \
  --header "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  --header 'Content-Type: application/json' --data "$purge_payload" --output "$purge_response"
jq -e '.success == true' "$purge_response" >/dev/null

for path in "$repository.db" "$repository.db.sig"; do
  curl --fail --silent --show-error --location \
    "https://packages.meoarch.org/$repository/os/x86_64/$path" --output /dev/null
done
echo "Published and remotely verified $repository metadata"
