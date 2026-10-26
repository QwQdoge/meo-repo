# MeoArch on the AUR (`yay`)

MeoArch has two install paths, used for different jobs:

- **Everything:** configure the signed Meo repository (`packages.meoarch.org`, channels `meo` and `meo-beta`) and manage
  the whole software set with pacman (see the workspace README, `scripts/install.sh`).
- **One piece of software:** install it on its own from the AUR with `yay -Syu <package>`. Always use `-Syu`, never a
  bare `-S`, so the system is never partially upgraded.

AUR packages are rendered from the same reviewed release manifests as the pacman packages: same version, same pinned
source commit and SHA-256 (`scripts/publish_aur.py`).

## Packages

| AUR package | Source | Notes |
| --- | --- | --- |
| `meoui-qml` | `QwQdoge/MeoUI` | Qt Quick / QML Material Design 3 design system (MIT). |
| `meo-icons`, `meo-icon-studio`, `meo-kde-runtime`, `meo-desktop` | `QwQdoge/meo-kde` | MeoKDE: icons, tooling, system runtime, and the desktop. |
| `meo-settings` | `QwQdoge/MeoSettings` | Meo Settings; needs `meo-account` (below). |
| `meo-repair` | `QwQdoge/MeoArch-os-workspace` | Quick Repair application. |
| `omnistore-bin` | OmniStore release bundle | The prebuilt native release bundle from GitHub Releases. |
| `meo-plasma-login-manager` | `QwQdoge/meo-login-manager` | Meo Login; conflicts with and replaces `plasma-login-manager`. |
| `meo-account-bin` | published Meo repository package | `meo-account` has private source, so this repackages the signed binary and provides `meo-account`. |

Not on the AUR: `meo-ai` (heavy Rust and Python build; use the Meo repository for now) and the repository plumbing
packages (`meo-release`, `meo-keyring`, `meo-mirrorlist`, `meo-channel-*`, the `*-meta` packages).

## Install

```bash
yay -Syu meo-desktop meo-settings omnistore-bin
```

## Publishing

`release.yml` has a `publish-aur` job that runs after a **complete Stable** train (`candidate` empty) has published and
passed the remote pacman smoke. It uses the protected `release` environment and the repository secret `AUR_SSH_KEY`
(an SSH private key whose public half is registered on the AUR account). Without the secret it only prints a warning;
it never fails a release. Beta never publishes to the AUR. A manual run:

```bash
AUR_SSH_KEY_FILE=~/.ssh/meoarch_aur python3 scripts/publish_aur.py publish manifests/stable/<release>.json WORKDIR \
  --also manifests/beta/<latest>.json --push
```

`--also` supplies components that the Stable train does not contain (for example `meo-kde-runtime`).

One-time setup (by the AUR account owner):

1. `ssh-keygen -t ed25519 -N '' -C meoarch-aur-publish -f aur_key`
2. Add `aur_key.pub` under AUR → My Account → SSH Public Key (the AUR asks for the account password).
3. Add the private key as the GitHub Actions secret `AUR_SSH_KEY` of `QwQdoge/meo-repo`, then delete the local copy.

Notes: the CI job publishes from the Stable manifest only; add `--also` (latest Beta manifest) in the workflow if the
Stable train omits a dependency. `meo-account-bin` downloads the published package, so publish the pacman repository
first.
