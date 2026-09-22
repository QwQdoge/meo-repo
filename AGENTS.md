# MeoArch Package Repository agent rules

This is the package-control worktree. Preserve package sources, release
manifests, keyring inputs, and the tracked x86_64 repository payload.

## Source ownership

- Keep Arch package recipes and package-owned files in packages/.
- Keep release inputs in manifests/, checks in scripts/ and tests/, and
  code-bound release/key-management contracts in docs/.
- Treat x86_64/ as retained repository state, not as an unowned build cache.
- Do not vendor source from MeoUI, MeoKDE, OmniStore, or another component
  repository into a package recipe without an explicitly scoped packaging task.

## Portable workspace roots

- Never assume a developer username, home directory, checkout location, or Obsidian vault path.
- Resolve external project records from `$MEO_DOCS_ROOT` and generated artifacts from `$MEO_OUTPUT_ROOT`. If either variable is unset, do not invent a machine-specific absolute path.

## Documentation and records

- Do not create root-level plan files, audits, architecture drafts, agent
  journals, screenshots, logs, or temporary notes.
- Store plans, decisions, audits, and historical reports in
  `$MEO_DOCS_ROOT/Projects/meo-repo/`, using
  00-inbox, 01-overview, 02-decisions, 03-work, 04-validation, and 99-archive.
- Existing documentation and payloads are preserved. Do not move or delete
  them as incidental cleanup.

## Output rules

Write new durable output only under `$MEO_OUTPUT_ROOT/meo-repo/`:

| Kind | Path |
| --- | --- |
| Build work | build/ |
| Repository/install handoff | install/ |
| Validation evidence | validation/<UTC-run-id>/ |
| Candidate packages | packages/ |
| Disposable work | tmp/ |

Use YYYY-MM-DDTHHMMSSZ-short-label for every validation run.

## Signing and publication boundary

- Never add private keys, passphrases, tokens, or credentials to source,
  external project records, or outputs.
- Do not sign packages, mutate the repository database, publish a channel,
  upload artifacts, or replace remote repository content without explicit user
  authorization.
- Preserve dirty work and avoid git reset, git clean, broad deletion, or
  unreviewed recursive commands.
- State whether validation covered recipe syntax, local build, signed package,
  repository metadata, and real installation; do not collapse these levels.
