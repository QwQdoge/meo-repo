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

## Publishing (automatic)

After a **complete Stable** train has published and passed the remote pacman smoke, `release.yml` calls
`publish-aur.yml`, which renders every AUR package from the released manifest (plus the latest Beta manifest for
components the Stable train lacks) and pushes the ones that changed. The job runs in the protected `release`
environment (so it needs the same approval) and reads the SSH key from the `release` environment secret
`AUR_SSH_KEY`; the public half is registered on the AUR account. Without the secret it only warns and never fails a
release. Beta never publishes to the AUR. Re-running is idempotent: unchanged packages are reported as up to date.

Run it by hand for an already released manifest:

```bash
gh workflow run publish-aur.yml -R QwQdoge/meo-repo -f manifest=manifests/stable/<release>.json
```

or locally:

```bash
AUR_SSH_KEY_FILE=~/.ssh/meoarch_aur python3 scripts/publish_aur.py publish manifests/stable/<release>.json WORKDIR \
  --also manifests/beta/<latest>.json --push
```

Rotating the key: generate a new ed25519 key, replace the public key under AUR → My Account → SSH Public Key (the AUR
asks for the account password), then `gh secret set AUR_SSH_KEY --env release -R QwQdoge/meo-repo < new_key`.

`meo-account-bin` downloads the published package, so the pacman repository is published first (the workflow order
guarantees this).
