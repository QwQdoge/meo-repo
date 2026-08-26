# Meo keyring release input

Place only reviewed **public** files here before a protected release:

- `meo.gpg`
- `meo-trusted`
- `meo-revoked`

The offline master private key and CI signing subkey must never be placed in
this directory. `scripts/validate_keyring_payload.py` fails closed until all
three public payloads are present and non-empty.
