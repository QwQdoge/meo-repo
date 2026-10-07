# Input-method capability catalog

`manifests/input-method-capabilities.json` is the versioned package-capability input shared by MeoArch components that need to plan supported input-method installation.

It is **not** an installed-state database and it is not a promise that every named package exists in every configured repository at every moment.

## Ownership

- `meo-repo` owns stable capability IDs and the package names that can satisfy them.
- Installer and Meo Settings may request a framework/engine capability by ID.
- The package transaction authority resolves the listed package names against the repositories actually configured on the target, reports availability/source/size/dependencies, obtains authorization when required, applies the transaction, and verifies the resulting installed capability.
- `meo-kde` owns the logged-in runtime integration and Fcitx state adapter after the packages are present.

Consumers must not turn this manifest into a second package manager or assume that a catalog entry is installed merely because it exists here.

## Version 1

The first catalog describes the supported Fcitx 5 path:

- framework: `fcitx5`;
- optional Qt and GTK toolkit bridges;
- optional upstream configuration tool for specialist fallback;
- Chinese: Pinyin, Rime, Chewing/Zhuyin, and repository table collections;
- Japanese: Mozc, Anthy, SKK, and KKC;
- Korean: Hangul;
- Vietnamese: UniKey and Bamboo;
- Sinhala: Sayura;
- M17N multilingual engines.

These entries are discovery capabilities, not default-install requirements. A clean Meo Desktop can ship the Fcitx framework and toolkit bridges while installing none of the optional language engines until the user requests one.

The package names are intentionally **not version-pinned**. Version selection, signatures, repository priority, dependency solving, mirrors, download size, and whether a package is currently available remain package-manager/repository responsibilities.

`sourcePolicy: configured-signed-repository` means an engine can be offered only when the active transaction authority resolves its package from a configured trusted repository. The catalog must not cause a consumer to download an arbitrary package file or execute an upstream installation script.

## Managed modes

`meo-managed` means MeoArch may manage the supported framework integration, runtime state, engine selection, and contextual package requests through its typed backends.

`self-managed` keeps the framework available but stops Meo from treating optional engine/configuration choices as managed product state.

Switching modes is a Settings/runtime concern. This catalog does not remove packages or user dictionaries and does not define destructive cleanup.

## Adding capabilities

When adding a framework or engine:

1. assign a stable ID that describes the capability, not a transient package version;
2. reference only repository package names, never commands, URLs, local paths, or shell fragments;
3. keep framework and engine package roles explicit;
4. use a trusted-source policy;
5. update the manifest contract tests;
6. let consumers detect actual repository availability at runtime.

Do not add speculative packages merely to make the catalog look complete. A specialist engine can remain undiscoverable until its ownership and supported repository path are clear.
