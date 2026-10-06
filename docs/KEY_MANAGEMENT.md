# Key-management runbook

## Release identity

The canonical package-archive signing identity for the current MeoArch release train is:

`MeoArch Package Archive <packages@meoarch.org>`

Trusted primary fingerprint:

`ACCF 58C0 05D4 67A0 C863 3806 F302 FD51 C406 16AA`

`MeoArch` is intentional here: this key authenticates the MeoArch distribution package archive, not a single Meo application. The signing UID and trusted primary fingerprint are release identity and must not be renamed merely for application-brand consistency.

Signing subkeys may rotate beneath this trusted primary key. Any rotation must preserve the reviewed trust path and use the normal release procedure.

## Operations

1. Generate and keep the MeoArch package-archive master certification key offline. The offline primary private key never enters source control or CI.
2. Create a package/database signing subkey and import only that subkey into the protected `release` GitHub Environment.
3. Export public `meo.gpg`; write public full-fingerprint ownertrust metadata to `meo-trusted`; and write public full fingerprints of retired keys to `meo-revoked` into `packages/meo-keyring/files/`. Review every fingerprint in a protected pull request.
4. Revoke/rotate a compromised subkey by updating `meo-revoked`, publishing a new keyring from stable, and using the documented ISO bootstrap update.
5. Changing the trusted primary key or its canonical archive identity is a separate migration. It requires an explicit bootstrap/trust transition plan and must never be performed as a cosmetic branding change close to release.

Build jobs never receive a private master GPG key, R2 credential, or deployment token.
