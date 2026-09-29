# MeoArch Package Repository agent rules

## Start here

This repository owns package recipes, release manifests, validation tooling, keyring inputs, and the tracked repository payload. Inspect `git status`, the affected package/manifest/script, and its nearest test before editing. Do not audit every package or read all release history by default.

## Ownership

- `packages/`: Arch package recipes and package-owned files.
- `manifests/`: reviewed release inputs.
- `scripts/`, `ci/`, `tests/`: validation/repository tooling and contracts.
- `docs/`: maintained release/key-management contracts.
- `x86_64/`: retained repository state, not disposable cache.

Do not vendor MeoUI, MeoKDE, OmniStore, or another project into package recipes unless the task is explicitly about packaging that source.

## Validation matrix

For normal package/repository source changes, mirror `.github/workflows/validation.yml`:

- `python -m compileall -q scripts tests`
- `python -m unittest discover -s tests -v`
- `find ci scripts -type f -name '*.sh' -print0 | xargs -0 -n1 bash -n`

For a single recipe or manifest, run the narrowest matching test first. Use `namcap`, package builds, or install smoke only when that layer changed and the required environment is available.

`.github/workflows/repository-smoke.yml` talks to the **published** repository. Do not run remote repository smoke as a substitute for local source validation, and do not run it unless the task explicitly needs published-repository evidence.

## Signing and publication boundary

Never expose private keys, passphrases, signing material, tokens, or credentials. Do not sign packages, mutate repository databases, publish stable/beta channels, upload artifacts, or replace remote repository content without explicit authorization.

Keep recipe syntax, local build, signed package, repository metadata, remote install, and live upgrade as separate evidence levels.

## Files and generated output

Keep maintained contracts in `docs/`. Project records belong under `$MEO_DOCS_ROOT/Projects/meo-repo/`; generated output under `$MEO_OUTPUT_ROOT/meo-repo/{build,install,validation,packages,tmp}/`. Do not invent machine-specific paths if those roots are unset.

Preserve unrelated dirty work and existing tracked repository payloads. Avoid destructive Git cleanup or broad deletion.
