# MeoArch Package Repository agent rules

## Scope

This repository owns package recipes and package-owned files in `packages/`, release inputs in `manifests/`, validation tooling in `scripts/` and `tests/`, and the retained `x86_64/` repository payload. Do not vendor source from MeoUI, MeoKDE, OmniStore, or another component unless the task is explicitly about packaging that source.

## Work sequence and validation

Inspect the affected recipe/manifest/script and `git status` before editing. For normal repository-contract changes, mirror CI:

- `python -m compileall -q scripts tests`
- `python -m unittest discover -s tests -v`
- syntax-check affected shell entrypoints (CI checks `ci/` and `scripts/`)

A recipe syntax/static check, a local package build, a signed package, repository metadata, and a real install are distinct evidence levels. Run the heavier build/install level only when the task requires it.

Use `$MEO_DOCS_ROOT/Projects/meo-repo/` for plans/audits/decisions and `$MEO_OUTPUT_ROOT/meo-repo/{build,install,validation,packages,tmp}/` for generated output. Keep generated material out of the repository root and preserve existing payloads/history.

Never place private keys, passphrases, tokens, or credentials in source or outputs. Do not sign packages, mutate the repository database, publish a channel, upload artifacts, or replace remote repository content without explicit authorization. Avoid `git reset`, `git clean`, and broad deletion.
