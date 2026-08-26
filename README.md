# MeoArch Package Repository

This repository is the MeoArch package-control worktree. It contains package
recipes, release manifests, validation helpers, keyring payload inputs, and the
tracked repository payload used by MeoArch package publication workflows.
Component implementation source stays in its owning project and must not be
vendored here as a shortcut.

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
| Plans, audits, decisions, agent journals, and historical reports | /home/shekong/Documents/Obsidian Vault/MeoArch/Projects/meo-repo/ |
| Reproducible build work | /home/shekong/Projects/outputs/meo-repo/build/ |
| Install/repository handoff material | /home/shekong/Projects/outputs/meo-repo/install/ |
| Validation evidence | /home/shekong/Projects/outputs/meo-repo/validation/<UTC-run-id>/ |
| Candidate packages and publication bundles | /home/shekong/Projects/outputs/meo-repo/packages/ |
| Disposable generated work | /home/shekong/Projects/outputs/meo-repo/tmp/ |

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
