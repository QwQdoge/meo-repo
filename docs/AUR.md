# MeoArch on the AUR (`yay`)

The AUR is an extra install path next to the signed Meo pacman repository (`packages.meoarch.org`, channels `meo` and
`meo-beta`). AUR packages are rendered from the same reviewed release manifests as the pacman packages: same version,
same pinned source commit and SHA-256 (`scripts/publish_aur.py`).

## Which packages

Only components that build from **public** sources and depend on Arch/AUR packages go to the AUR.

| AUR package | Source | Notes |
| --- | --- | --- |
| `meoui-qml` | `QwQdoge/MeoUI` | Qt Quick / QML Material Design 3 design system (MIT). |
| `meo-plasma-login-manager` | `QwQdoge/meo-login-manager` | Meo Login; conflicts with and replaces `plasma-login-manager`. |

Not published to the AUR, by design: `meo-account` (private source), the meta/channel/keyring packages (they only make
sense with the Meo repository), and packages that depend on those (`meo-settings`, `meo-ai`, `omnistore-bin`). Install
those from the Meo repository.

## Install

```bash
yay -Syu meoui-qml meo-plasma-login-manager
```

(only after the packages are live on the AUR; check `https://aur.archlinux.org/packages/meoui-qml`).

## Publishing

`release.yml` has a `publish-aur` job that runs after a **complete Stable** train (`candidate` empty) has published and
passed the remote pacman smoke. It uses the protected `release` environment and the repository secret `AUR_SSH_KEY`
(an SSH private key whose public half is registered on the AUR account). Without the secret it only prints a warning;
it never fails a release. Beta never publishes to the AUR. A manual run (`publish_aur.py publish MANIFEST WORKDIR
--push`) uses the key file named in `AUR_SSH_KEY_FILE`.

One-time setup (by the AUR account owner):

1. `ssh-keygen -t ed25519 -N '' -C meoarch-aur-publish -f aur_key`
2. Add `aur_key.pub` under AUR → My Account → SSH Public Key (the AUR asks for the account password).
3. Add the private key as the GitHub Actions secret `AUR_SSH_KEY` of `QwQdoge/meo-repo`, then delete the local copy.
