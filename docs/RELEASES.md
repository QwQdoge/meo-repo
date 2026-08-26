# Release operations

`stable` accepts a protected, fully pinned manifest only.  `beta` accepts one
reviewed candidate manifest and writes only the affected package to `meo-beta`.
The publishing worker downloads the current DB, applies `repo-add`/`repo-remove`
locally, signs it, and uploads package objects before mutable DB objects.

Repository objects are laid out as:

```text
meo/os/x86_64/{package.pkg.tar.zst,package.pkg.tar.zst.sig,meo.db,meo.db.sig,meo.files,meo.files.sig}
meo-beta/os/x86_64/{package.pkg.tar.zst,package.pkg.tar.zst.sig,meo-beta.db,meo-beta.db.sig,...}
```

`*.pkg.tar.zst` objects are immutable and may be long cached. Database and
files DB objects are mutable and must use `no-cache` (or a very short TTL) and
be purged only after their referenced packages and signatures are reachable.
Publishing is serialized per channel. Build jobs are untrusted and receive no
GPG private key or R2 write credential; the protected signing job verifies the
artifact hash before it signs or uploads anything.

After a Stable publication, compare every same-name beta overlay entry with
the Stable candidate using pacman's `vercmp`. If Stable is equal or newer,
remove that package from `meo-beta` with `repo-remove`, re-sign the beta DB,
publish it serially, and verify the Stable fallback. Never mirror all Stable
packages into `meo-beta`.

Never publish a package solely because a source branch changed.  Create source
tags, pin their commits and checksums in the manifest, and approve the protected
release environment.  The sample manifest deliberately contains placeholders
and is expected to fail validation until a release manager replaces them.
