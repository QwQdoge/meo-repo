# Meo platform generations

`manifests/platform-generation.schema.json` and
`scripts/validate_platform_generation.py` define the release gate for a Meo
desktop session-core compatibility train.  A platform generation is not a
loose set of packages: it is one exact, hash-bound closure that can be reviewed
before Beta/Stable publication and before installer resolution.

## Required content

Each published `manifests/platform-generations/<generation>-<train>.json`
uses schema version 1 and records:

- `meoui-qml`, `meo-lockscreen`, `meo-login-manager`, `meo-desktop`,
  `meo-settings`, and `meo-core-meta` as exact Meo package artifacts;
- `kscreenlocker`, `plasma-workspace`, `plasma-desktop`, `kwin`, `qt6-base`,
  `qt6-declarative`, and `kf6-kconfig` as exact, read-only Arch snapshot roots;
- the complete resolved dependency closure, HTTPS source URL, package version
  and SHA-256 for every artifact; and
- an atomic update policy: core packages cannot use `IgnorePkg` or a partial
  core upgrade.

The root list is the compatibility floor, not the whole closure.  Package
resolution must include every dependency of every listed package.  The
validator rejects a missing root, duplicate package, unpinned archive hash,
replacement of a preserved KDE security/runtime package, incomplete Meo core,
or a non-atomic policy.

## Replacement and preservation

`meo-login-manager` is the only replacement for `plasma-login-manager`.
`kscreenlocker`, `plasma-workspace`, `plasma-desktop`, and `kwin` are preserved
runtime packages and cannot appear in `replacedPackages`.  A later SDDM
migration may record SDDM and `sddm-kcm` as a single reviewed transaction, but
it must not enter a generation until reverse dependencies, rollback and an
installed-system migration are verified.

`meo-core-meta` remains the installer's only session-core entry package.
`meo-desktop` must depend on both `meo-lockscreen` and `meo-login-manager` in
the same generation; OmniStore must diagnose a mixed generation and route the
user to a full signed train update or an approved rollback, never a local
core-package upgrade.

## Publication boundary

There is intentionally no `6.7` generation manifest yet.  P0 does not invent
package versions, an Arch snapshot, dependency closure or SHA-256 values before
the packages exist.  P5 creates a manifest only after reproducible package
builds and closure resolution, validates it with:

```bash
python3 scripts/validate_platform_generation.py manifests/platform-generations/<generation>-<train>.json
```

That check validates metadata, not a signed repository, VM boot, real lock
screen, display-manager switch or a real-machine login.  Those remain separate
release gates.
