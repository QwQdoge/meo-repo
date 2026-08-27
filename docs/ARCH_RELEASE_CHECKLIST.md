# Arch release-machine checklist

This runbook contains only work which requires Arch Linux, offline key custody,
GitHub protected environments, Cloudflare R2, or VM/ISO infrastructure. The
repository scripts deliberately fail before signing or publication until these
inputs exist.

## 1. Create real immutable component releases

Do not force-create the old placeholder tags. Create reviewed tags from the
commits intended for the first release train and record the full 40-character
commit IDs.

Current blockers observed on 2026-08-27:

- `QwQdoge/MeoUI` has no `v1.0.2` remote tag.
- `QwQdoge/meo-kde` has no `v0.3.0` remote tag.
- `QwQdoge/MeoSettings` has no `v0.1.0` remote tag.
- OmniStore `v0.1.2` exists, but that tag does not contain
  `verify_release_exporter_contract.py`; create a newer release/tag whose bundle
  and verifier satisfy the current exporter contract.

For every component, download the immutable commit archive or release bundle
once and record its SHA-256. Source packages must use a commit-bound archive
URL. OmniStore must use a release-bundle URL plus a verifier URL bound to the
same pinned commit.

Fill every field in `manifests/stable/<release>.json`, then run:

```bash
python scripts/validate_manifest.py manifests/stable/<release>.json
python scripts/verify_manifest_sources.py manifests/stable/<release>.json
```

Both must pass. `expectedVersion` must exactly match `pkgver-pkgrel` in its
PKGBUILD.

## 2. Establish the offline trust root

On an offline machine:

1. Generate a certification-only master key.
2. Create a time-limited signing subkey dedicated to package/repository CI.
3. Record both fingerprints offline and prepare a revocation certificate.
4. Export only the CI signing subkey for GitHub; never export the master secret
   key to an online machine. The exported CI-only copy must be usable in an
   unattended protected job (no interactive passphrase prompt). Treat the
   Environment approval, short expiry and revocation capability as the
   compensating controls; never remove protection from the offline master key.
5. Export the public pacman keyring files as `meo.gpg`, `meo-trusted`, and
   `meo-revoked`.

Review and commit only the public files under:

```text
packages/meo-keyring/files/
```

Copy the same reviewed payload into the ISO release input at:

```text
MeoArch_os-workspace/installer/bootstrap/
```

Run on Arch:

```bash
python scripts/validate_keyring_payload.py packages/meo-keyring/files
pacman-key --gpgdir "$(mktemp -d)" --init
# In a disposable root, install the three files under
# /usr/share/pacman/keyrings and run: pacman-key --populate meo
```

`ci/build-release.sh` renders exact payload SHA-256 values into the temporary
meo-keyring build context. The committed PKGBUILD never contains private key
material.

## 3. Configure Cloudflare R2

Create or confirm:

- one R2 bucket scoped to the package repository;
- custom domain `packages.meoarch.org`;
- an R2 API token restricted to Object Read & Write for that bucket;
- a Cloudflare API token restricted to cache purge for the package zone.

The workflow uses the documented S3-compatible R2 endpoint. Store these only
in the GitHub `release` Environment:

```text
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_ENDPOINT
R2_BUCKET
CLOUDFLARE_ZONE_ID
CLOUDFLARE_API_TOKEN
MEO_GPG_SIGNING_SUBKEY_B64
MEO_SIGNING_KEY_FINGERPRINT
```

Configure required reviewers for the `release` Environment. Build jobs must
not have access to that environment. R2 and purge Secrets are scoped to the two
shell steps which need them, not the whole job. Official GitHub actions in the
workflow are pinned to reviewed 40-character commits; update those pins only in
a separately reviewed change.

Package objects are uploaded with a one-year immutable Cache-Control value.
DB/files objects and their signatures use `no-cache,max-age=0,must-revalidate`.
After mutable objects are uploaded, the workflow purges only their exact URLs.
Cloudflare documents R2's S3-compatible endpoint and Cache-Control metadata at
<https://developers.cloudflare.com/r2/api/s3/api/> and recommends single-file
purging at <https://developers.cloudflare.com/cache/how-to/purge-cache/>.

## 4. First repository initialization

The first Stable workflow creates a complete DB from all five core packages
plus the five control packages. Do not publish a partial Stable artifact.

The first Beta publication additionally requires the protected GitHub
Environment variable:

```text
ALLOW_INITIAL_BETA_REPOSITORY=1
```

Remove or set it to `0` immediately after the first successful Beta DB publish.
Later Beta runs download and verify the existing signed DB before merging one
candidate, preserving other sparse overlays.

## 5. Dispatch and monitor releases

Stable:

```text
channel=stable
manifest=manifests/stable/<release>.json
beta_candidate=<empty>
```

Beta:

```text
channel=beta
manifest=<reviewed manifest containing the candidate identity>
beta_candidate=<exactly one core package name>
```

The workflow now performs:

```text
unprivileged Arch build and project packaging
→ namcap and installed smoke
→ hash-bound unsigned artifact
→ protected artifact and internal package metadata re-verification
→ package signing and immutable upload
→ remote object existence check
→ repo-add and DB signing
→ mutable DB upload
→ exact-URL cache purge
→ remote signed pacman install smoke
```

After Stable publication, `ci/cleanup-beta-overlay.sh` verifies both repository
DB signatures, compares same-name versions with Arch `vercmp`, and runs
`repo-remove` only for Beta entries which Stable has reached or surpassed.

## 6. Required negative tests on Arch

Use disposable pacman roots/containers. Preserve logs without secrets.

- unsigned package is rejected;
- package signed by an unknown key is rejected;
- tampered package signature is rejected;
- unsigned DB is rejected;
- tampered DB signature is rejected;
- DB referencing a nonexistent package fails installation;
- Stable has only `meo`; Beta resolves `meo-beta` before `meo`;
- Beta fallback installs a package available only in Stable;
- the two channel packages conflict and never auto-replace each other;
- Stable publication removes an obsolete Beta overlay;
- existing immutable R2 package object cannot be overwritten with different
  content;
- every repository publication serializes rather than cancels. This global
  lock is required because a Stable run also mutates the Beta DB during overlay
  cleanup.

## 7. ISO/VM acceptance

Build the ISO only after a signed Stable repository exists. Verify at least:

```text
Stable Recommended install
Stable Minimal install
Beta Recommended install and Stable fallback
Custom dependency closure
GUI/CLI InstallConfig parity
invalid DB/package signature preflight failure before disk mutation
installed pacman-conf channel order
OmniStore and MeoSettings channel agreement
Stable → Beta normal upgrade
Beta → Stable Meo-only downgrade with no Arch package downgrade
```

The final Beta → Stable local signed-package downgrade executor in OmniStore is
still not implemented. Do not mark that acceptance case passed until it can
download exact Stable package files, verify them, preview the complete libalpm
transaction, and abort on any non-Meo removal/replacement/downgrade.

## 8. Implement and validate the final OmniStore Stable rollback on Arch

Do this in `OmniStore/python/core/meo_channel.py`; do not create a second
channel state or a separate package manager. The existing first transaction
which installs `meo-channel-stable`, refreshes databases, reads the
`meo-release` catalog and returns `confirmation_required` stays in place.

Use libalpm for the remaining resolver boundary. If the bundled Python runtime
cannot import the system `pyalpm`, add one narrow root helper executed with the
system Python and package it with OmniStore; add `python-pyalpm` as a runtime
dependency. The helper must accept only a versioned JSON request on stdin and
must reject unknown keys/package names. It must not accept arbitrary pacman
arguments, repository URLs or shell text.

Required second-stage algorithm:

1. Acquire the pacman DB lock and reopen the effective configuration after the
   channel-package transaction. Confirm the Meo repository subsequence is
   exactly `meo` and contains no `meo-beta`.
2. Load the official set only from
   `/usr/share/meo-release/package-catalog.json`; validate every name with the
   existing package-name grammar.
3. For each installed official package, resolve the exact candidate from the
   `meo` sync DB. Build the downgrade target set from libalpm version
   comparison, not lexical comparison and not a `meo-` prefix.
4. Download those exact package files into a newly created root-owned staging
   directory. Require the configured `Required TrustedOnly` policy and perform
   full package signature verification before transaction preparation.
5. Prepare, but do not commit, one local-package libalpm transaction. Inspect
   every `to_add` and `to_remove` entry and every replacement/conflict result.
   Abort unless all changed package names are in the catalog, every addition is
   the exact reviewed Stable version, and there are no Arch/third-party
   removals, replacements, upgrades or downgrades.
6. Return a preview containing package name, installed version, Stable version,
   package SHA-256 and a canonical plan hash. The Flutter dialog must display
   the complete list and request the existing second confirmation.
7. On confirmation, reacquire the lock, reopen libalpm, resolve again, and
   require the same plan hash. Any repository/installed-state drift invalidates
   the confirmation and returns a fresh preview.
8. Commit only that prepared local-package transaction. Never invoke `-Suu`.
   Remove the staging directory on success or failure and return the final
   `pacman-conf --repo-list`-derived status.

Required tests in a disposable Arch root:

- Beta package newer than Stable produces an exact downgrade preview;
- confirmation commits only the listed official Meo packages;
- `omnistore-bin` is included even though it lacks the `meo-` prefix;
- a dependency which would install/remove/replace/downgrade a non-Meo package
  aborts before commit;
- tampered/unknown/unsigned package aborts;
- plan drift between preview and confirmation aborts;
- pacman lock contention returns a retryable error;
- partial download, disk full and transaction failure preserve a valid Stable
  repository configuration and do not claim rollback success.

Until these tests pass on Arch, the present refusal is the safe production
behavior and this acceptance item remains `NOT VERIFIED`.
