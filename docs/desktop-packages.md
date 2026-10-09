# Desktop package contract

`meo-repo/packages/` owns distribution recipes. Component source stays in its
own repository; MeoKDE exports `tools/session/package-meo-desktop` as its payload
interface. Its `packaging/arch` recipe is only a source-checkout convenience.

| Package | Responsibility |
| --- | --- |
| `meoui-qml` | Shared MeoUI controls and exported token SDK |
| `meo-icons` | Shared icon themes |
| `meo-desktop` | Independent Meo Desktop session, private shell/style/defaults, passive public application imports |
| `meo-kde-runtime` | Minimal application imports when the full desktop is absent; replaced by `meo-desktop` |
| `meo-plasma-login-manager` | Meo OS login presentation; installed by the ISO profile, not a desktop dependency |

Installing the desktop must not apply a look-and-feel to the current session,
reset the user's panels, enable global color/weather services, change PAM, or
replace the display manager. The session entry calls `start-meo-desktop`, which
seeds a separate user profile without overwriting existing preferences. KDE,
KWin and Plasma remain upstream packages and receive normal Arch updates.

## Local candidates

Commit the component changes, then render a normal makepkg context:

```bash
python3 scripts/stage_local_component.py meo-desktop "$MEO_KDE_ROOT" \
  "$MEO_OUTPUT_ROOT/meo-repo/build/desktop-candidate"
cd "$MEO_OUTPUT_ROOT/meo-repo/build/desktop-candidate"
makepkg --syncdeps
```

The rendered `PKGBUILD` has an ordinary `source` archive and `sha256sums`;
makepkg verifies and extracts it normally. `.SRCINFO` and source provenance
record the exact committed snapshot. Dirty trees and existing output contexts
are rejected. Build `meoui-qml` first, then `meo-icons`, then `meo-desktop`.
Build the login package separately for the ISO. Use a disposable build system
for dependency installation; the staging tool itself does not install anything.

Generated archives belong in `$MEO_OUTPUT_ROOT/meo-repo/packages/`. These are
unsigned local candidates, not a published channel. Frozen release manifests
and retained repository payloads are not rewritten by candidate staging.

## Installed system and ISO

After a signed channel publishes this package set, the public workspace
`scripts/install.sh --full` installs the recommended profile and adds **Meo
Desktop** to the login chooser. `--core` omits the optional application bundle.
The bootstrap refuses a channel without `meo-desktop-session=1` before installing
the desktop profile. Normal updates use pacman/OmniStore.

The ISO profile additionally selects `meo-plasma-login-manager`, verifies package
availability and independent-session support before disk operations, installs
OS policy on the fresh target, and preselects Meo Desktop at first login. Package
builds and target-file checks do not prove ISO boot, real PAM authentication, or
first desktop startup; those require a VM or hardware installation.
