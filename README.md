# MeoArch Package Repository

This repository is the MeoArch package-control worktree. It contains package
recipes, release manifests, validation helpers, keyring payload inputs, and the
tracked repository payload used by MeoArch package publication workflows.
Component implementation source stays in its owning project and must not be
vendored here as a shortcut.

## License

The original package recipes, manifests, validation helpers, and repository
automation in this repository are licensed under the MIT License; see
[LICENSE](LICENSE). This license does not relicense packaged components,
vendored upstream material, public keys, or generated package payloads. Those
retain their own licenses and terms.

## What is in this repository

| Path | Purpose |
| --- | --- |
| packages/ | Arch package recipes, channel packages, mirror/keyring inputs, and package-owned files. |
| manifests/ | Versioned package catalog and release-train inputs. |
| scripts/ | Manifest, overlay, and keyring validation helpers. |
| tests/ | Host-independent release-contract tests. |
| docs/ | Key-management and release-operation contracts. |
| x86_64/ | Deliberately retained, tracked repository database/files/package payload. It is not scratch output. |

README.md and AGENTS.md are the human/agent entry points. Root-level package
tool configuration remains when required. Do not add project plans, review
reports, architecture drafts, screenshots, or build logs to the root.

The single copyable cross-repository implementation and Arch release runbook is
[`docs/MEOARCH_IMPLEMENTATION_RUNBOOK.md`](docs/MEOARCH_IMPLEMENTATION_RUNBOOK.md).
The current complete prerelease train is pinned in
[`manifests/beta/2026.09-beta.7.json`](manifests/beta/2026.09-beta.7.json); it
records every component's owning GitHub repository, immutable release tag,
commit, package version, source URL, and SHA-256.
Unpublished integration work after that frozen train targets Beta 8. A Beta 8
manifest is created only after every included component has an immutable tag,
commit, package version, source URL, and verified checksum.
Beta 8 is a stabilization train: compatibility, accessibility, failure-state,
packaging, and verification fixes are accepted with the first Stable train as
the acceptance target; unrelated feature expansion is deferred.
The current Stable system-migration train is pinned in
[`manifests/stable/2026.09.2.json`](manifests/stable/2026.09.2.json).

## Package-source boundary

Package recipes and their package-owned files are source. The x86_64 repository
payload is also retained source-of-record state for this worktree. Neither is a
cleanup target. Build candidates, temporary repository databases, and release
handoff files must first go to the shared outputs location until an explicit
release task approves publication.

The public keyring payload is intentionally reviewed rather than generated
blindly. Never place private keys, signing secrets, tokens, or storage
credentials in this repository or in a validation archive.

## Filing rule for new material

| Material | Required location |
| --- | --- |
| Package source, manifests, tests, and checked-in repository payload | Their existing owning directory in this repository. |
| Contract tied to package/release code | docs/. |
| Plans, audits, decisions, agent journals, and historical reports | $MEO_DOCS_ROOT/Projects/meo-repo/ |
| Reproducible build work | $MEO_OUTPUT_ROOT/meo-repo/build/ |
| Install/repository handoff material | $MEO_OUTPUT_ROOT/meo-repo/install/ |
| Validation evidence | $MEO_OUTPUT_ROOT/meo-repo/validation/<UTC-run-id>/ |
| Candidate packages and publication bundles | $MEO_OUTPUT_ROOT/meo-repo/packages/ |
| Disposable generated work | $MEO_OUTPUT_ROOT/meo-repo/tmp/ |

Use a UTC run identifier in the form YYYY-MM-DDTHHMMSSZ-short-label, such as
2026-08-26T143015Z-keyring-check. Use the
numbered folders in the Obsidian project directory for incoming material,
overview, decisions, work, validation, and archived history.

## Release safety

- Preserve packages/, manifests/, x86_64/, and the existing worktree. Do not
  remove package or repository state to make the checkout appear clean.
- Do not sign packages, rebuild/publish repository databases, upload packages,
  or change a package channel without explicit authorization.
- A local package build or contract test is not proof of a published or
  installable repository. Record the verified level and missing checks.
