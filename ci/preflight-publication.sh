#!/usr/bin/env bash
# Protected-job preflight which intentionally runs before any signing key or
# R2 credential is present. Prints only the verified contract SHA-256.
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
manifest="$(realpath -e -- "${1:?manifest path is required}")"
artifact_dir="$(realpath -e -- "${2:?artifact directory is required}")"
channel="${3:?stable or beta channel is required}"
case "$channel" in stable|beta) ;; *) echo "Invalid channel" >&2; exit 2 ;; esac

contract="$artifact_dir/artifacts.json"
packages="$artifact_dir/packages"
python3 "$repo_root/scripts/artifact_manifest.py" verify \
  --contract "$contract" --manifest "$manifest" --packages "$packages"
python3 "$repo_root/scripts/verify_package_metadata.py" \
  --contract "$contract" --packages "$packages"
contract_channel="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["channel"])' "$contract")"
[ "$contract_channel" = "$channel" ] || { echo "Artifact channel does not match publication channel" >&2; exit 3; }
python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$contract"
