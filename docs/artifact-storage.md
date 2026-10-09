# Package artifact storage policy

`meo-repo` currently tracks repository payload under `x86_64/`. That state remains authoritative until the signed R2-backed publication path is complete and an explicit migration is approved.

The long-term direction is to keep Git focused on reproducible source/release metadata while durable package artifacts live in release/object storage.

## Current authority

Until migration is complete:

- `packages/` owns Arch package recipes and package-owned files.
- `manifests/` owns reviewed immutable release inputs.
- release/validation tooling owns closure, source and publication checks.
- `x86_64/` is retained repository state and must not be deleted, regenerated casually, or treated as disposable cache.

## Target authority

After the R2 release pipeline is proven and explicitly cut over:

```text
Git repository
  packages/
  manifests/
  scripts/ ci/ tests/ tools/
  signing/publication metadata contracts

R2 / published package storage
  *.pkg.tar.zst
  *.pkg.tar.zst.sig
  repository database/files indexes
  immutable release/channel payloads
```

Git should not become the long-term binary package archive once object storage is the publication source of truth.

## Cut-over gates

Do not remove tracked package artifacts until all of the following are true:

1. package upload to R2 is deterministic and authenticated only inside the protected release environment;
2. repository database/files metadata is generated/published from reviewed immutable release inputs;
3. package signatures and checksums are verifiable after upload;
4. Beta and Stable channel resolution no longer depends on Git-tracked binary payload;
5. remote repository smoke/install/upgrade checks pass against the R2-backed endpoint;
6. rollback/recovery of a previously published channel is documented and tested;
7. release manifests retain enough immutable provenance to reproduce/audit what was published;
8. the migration is explicitly authorized because it changes publication/storage authority.

## Migration sequence

1. Keep `x86_64/` unchanged while R2 publication is introduced in parallel.
2. Make release workflows publish and then verify R2/object-storage artifacts.
3. Make clients/repository smoke consume the R2-backed endpoint.
4. Run at least one complete Beta release train through the new path; Stable should follow only after Beta evidence is satisfactory.
5. Freeze Git binary payload updates when R2 becomes authoritative.
6. Remove historical binary payload from normal Git tracking only in a dedicated repository migration, preserving provenance/tags/manifests as needed.

## Security boundary

No local GUI/tool or unprotected workflow should hold signing/R2/Cloudflare credentials. Release Center may validate and dispatch approved workflows, but signing and upload stay inside protected release infrastructure.

This document does not authorize publication, signing, channel mutation, artifact deletion, or R2 changes by itself.
