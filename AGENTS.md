## Workflow rules from the owner (override anything below)

- Commit directly on the repository's current/default branch (`main` unless the repo is deliberately on another working branch). Do not create feature branches or PR branches unless asked.
- After committing, push immediately. Do not ask for permission to commit or push, and do not leave finished work uncommitted or unpushed.
- Keep verification minimal: run only the quick check for the touched code (typecheck or the one relevant test). Do not run full suites or write extra tests unless asked.
- Do the whole task in one pass; do not stop to ask routine questions that have an obvious default.
- Never put secrets, tokens or credentials in code, logs or commits.

# MeoArch Package Repository agent rules

## Start here

This repository owns package recipes, release manifests, validation tooling, keyring inputs, and the tracked repository payload. Inspect `git status`, the affected package/manifest/script, and its nearest test before editing. Do not audit every package or read all release history by default.

Read `docs/artifact-storage.md` before changing `x86_64/` retention, R2/object-storage publication, repository database ownership, or binary-artifact tracking policy.

## Ownership

- `packages/`: Arch package recipes and package-owned files.
- `manifests/`: reviewed release inputs.
- `scripts/`, `ci/`, `tests/`, `tools/`: validation/repository/release tooling and contracts.
- `docs/`: maintained release/key-management/storage contracts.
- `x86_64/`: retained repository state and current tracked payload authority until the R2-backed cut-over defined in `docs/artifact-storage.md`; it is not disposable cache.

Do not vendor MeoUI, MeoKDE, OmniStore, or another project into package recipes unless the task is explicitly about packaging that source.

The long-term direction is for Git to own recipes/manifests/tooling and for protected release/object storage to own durable binary package/database artifacts. Do not delete or stop updating `x86_64/` before the documented cut-over gates are met and the authority change is explicitly authorized.

## Validation matrix

For normal package/repository source changes, mirror `.github/workflows/validation.yml`:

- `python -m compileall -q scripts tests`
- `python -m unittest discover -s tests -v`
- `find ci scripts -type f -name '*.sh' -print0 | xargs -0 -n1 bash -n`

For a single recipe or manifest, run the narrowest matching test first. Use `namcap`, package builds, or install smoke only when that layer changed and the required environment is available.

`.github/workflows/repository-smoke.yml` talks to the **published** repository. Do not run remote repository smoke as a substitute for local source validation, and do not run it unless the task explicitly needs published-repository evidence.

## Signing and publication boundary

Never expose private keys, passphrases, signing material, tokens, or credentials. Do not sign packages, mutate repository databases, publish stable/beta channels, upload artifacts, or replace remote repository content unless the owner asked for that release or change (an owner-requested release is fully authorized; see Shared workspace rules).

Keep recipe syntax, local build, signed package, repository metadata, remote install, and live upgrade as separate evidence levels.

Release Center or another local control surface may validate and dispatch approved workflows, but signing/R2/Cloudflare credentials and publication authority remain inside protected release infrastructure.

## Files and generated output

Keep maintained contracts in `docs/`. Project records belong under `$MEO_DOCS_ROOT/Projects/meo-repo/`. Existing package/test tools may use ephemeral work directories; retained evidence and deliverables belong under `$MEO_OUTPUT_ROOT/meo-repo/{build,install,validation,packages,tmp}/`. Do not invent machine-specific paths if those roots are unset.

Preserve unrelated dirty work and existing tracked repository payloads. Avoid destructive Git cleanup or broad deletion.

## Release dispatch and approval

- Beta builds one sparse candidate per run; dispatch each package separately with a reviewed manifest (`gh workflow run release.yml -f channel=beta -f manifest=manifests/beta/<release>.json -f candidate=<package>`). Runs share a non-cancelling lock and execute one after another, so N candidates take roughly N build durations (a run is typically 20-60 minutes).
- Before tagging a component, confirm its source archive extracts cleanly (no tracked build output such as `target/`, no absolute symlinks) and that its CI is green; tag the newest green commit, not blindly `main`.
- `sign-and-publish` and the AUR publish job wait on the protected `release` Environment (reviewer: the owner). Established agent path, once the owner has confirmed the release in chat: approve through the authenticated `gh` CLI, no browser needed:
  `gh api repos/QwQdoge/meo-repo/actions/runs/<run>/pending_deployments` (shows the environment id, currently 20640143512), then
  `gh api -X POST repos/QwQdoge/meo-repo/actions/runs/<run>/pending_deployments -F 'environment_ids[]=<id>' -f state=approved -f comment='Approved by owner via Claude: <package and manifest>'`.
  Approve only runs the owner just confirmed. Driving the GitHub UI in Chrome for the final "Approve and deploy" click is blocked by the tool permission layer; do not use it.

## MeoArch documentation map

- Docs site: https://meoarch.org/docs/ (MeoUI specification: app shell, settings pattern, page types, dynamic color, API lifecycle, localization). Agent entry points: https://meoarch.org/llms.txt and https://meoarch.org/docs/meoui/for-agents.md. The canonical source is the MeoUI repository `docs/`; if they disagree, the repository wins.
- Packaging and releases: https://github.com/QwQdoge/meo-repo - read its `AGENTS.md`, `docs/MEOARCH_IMPLEMENTATION_RUNBOOK.md`, `manifests/{beta,stable}/` and the "MeoArch repository release" workflow (https://github.com/QwQdoge/meo-repo/actions/workflows/release.yml).
- Release approval: the `sign-and-publish` job waits on the protected `release` Environment. After the owner confirms in chat, agents approve with `gh api -X POST repos/QwQdoge/meo-repo/actions/runs/<run>/pending_deployments -F environment_ids[]=<id> -f state=approved` (see meo-repo `AGENTS.md`); the owner can also use Actions -> "Review deployments" -> `release`.
- Before tagging a component for release: its source archive must extract cleanly (no tracked build output such as `target/`, no absolute symlinks) and its CI must be green; tag the newest green commit.
- Other repositories: MeoUI (design system), meo-kde (Plasma shell), meo-ai (Meo AI), meo-api (cloud API), MeoArch-account (account app), MeoSettings, MeoArch-os-workspace (ISO/installer/repair), OmniStore, meo-login-manager, meo-repo (packages), meoarch-site (meoarch.org).

## Shared workspace rules (owner)

Source: the owner's `projects/agent.md` (Windows `C:SERSMINGYUEPROJECTSGENT.MD`), repeated here on purpose. These rules apply to every repository and win over generic caution in the rest of this file.

- "All repositories" means: the `projects` folder inside WSL Arch (`~/projects`), the Windows `projects` folder, and whatever `gh repo list QwQdoge` shows; confirm with `gh`.
- Reading a repository: `git pull` and `git push` first so it matches the cloud. If there are open PRs/branches, merge all of them. If a branch is large or needs a decision, ask once, then merge everything without asking again before each merge; after merging, ask whether to run tests. Exceptions: old dependency-bump branches and branches that are clearly unneeded.
- Work: update dependencies to the newest versions dynamically; only if a bug survives a real fix attempt, roll back and tell the user. Never create working branches: one shared workspace on the default branch, kept tidy. Push every piece of work to the cloud right away; always `git pull` then `git push`, no delay.
- Ask the user as little as possible: anything solvable by a simple attempt, or that matches the user's stated wishes, is done without asking. Ask only after repeated real attempts show the goal cannot be reached.
- Read every relevant document before working: local ones and https://meoarch.org/docs/ (agent entry: https://meoarch.org/llms.txt).
- Releases the owner asks for are authorized end to end (tag, manifest, dispatch, approve via `gh api .../pending_deployments`); do not stop for extra approvals.
