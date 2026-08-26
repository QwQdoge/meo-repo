# Key-management runbook

1. Generate and keep the MeoArch master certification key offline.
2. Create a package/database signing subkey and import only that subkey into
   the protected `release` GitHub Environment.
3. Export public `meo.gpg`, ownertrust `meo-trusted`, and `meo-revoked` into
   `packages/meo-keyring/files/`; review the fingerprint in a protected pull
   request.
4. Revoke/rotate a compromised subkey by updating `meo-revoked`, publishing a
   new keyring from stable, and using the documented ISO bootstrap update.

Build jobs never receive a private GPG key, R2 credential, or deployment token.
