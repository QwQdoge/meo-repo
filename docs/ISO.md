# Live ISO distribution

The ISO has two download links. Both serve the same file and checksum.

| Link | Role | Where |
| --- | --- | --- |
| SourceForge | primary, keeps history | `https://sourceforge.net/projects/meoarch/files/` |
| Cloudflare R2 | backup mirror (reachable where SourceForge is blocked, for example some school networks) | `https://iso.meoarch.org/<file>` |

The R2 bucket `meo-iso` holds **exactly one ISO**, the newest, with its `.sha256` and a
`latest.json` (`name`, `sha256`, `size`) that the websites can read. It stays well inside the
free 10 GB. SourceForge keeps older builds.

## Publishing a new ISO

1. Build and verify the ISO as described in `AGENTS.md` (§ ISO 与 Live).
2. Upload to SourceForge (primary).
3. Publish to the R2 mirror. This needs an R2 API token (Object Read & Write, limited to
   `meo-iso`); only the owner holds it:

   ```bash
   export R2_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
   export AWS_ACCESS_KEY_ID=...   AWS_SECRET_ACCESS_KEY=...
   ci/publish-iso.sh /path/to/meoarch-os-YYYY.MM.DD-HHMMSS-x86_64.iso
   ```

   The script checks the `.sha256` next to the ISO, uploads, compares the stored size, writes the
   checksum and `latest.json`, and only then deletes every other ISO in the bucket. A failed upload
   therefore never leaves the mirror empty. Tests: `python3 -m unittest tests/test_publish_iso.py`.
4. Update the download cards (file name, date, SHA-256) on `MeoArch-os-webside` and `meoarch-site`;
   keep both links on each card.
5. Check the mirror: `curl -sI https://iso.meoarch.org/<file>` returns `200` with the right
   `content-length`, and `sha256sum` of a download matches.

## Setup (once)

- Bucket `meo-iso` (created 2026-10-26, Standard class). First ISO published the same day.
- Custom domain `iso.meoarch.org` attached to the bucket (R2 > meo-iso > Settings > Custom domains).
  Do not use the `r2.dev` URL: it is rate limited and not meant for distribution.
- Cloudflare does not charge egress for R2; the free tier covers 10 GB storage.

## Owner's machine

The bucket token (`meo-iso-publish`, Object Read & Write, `meo-iso` only) is kept in
`~/.config/meo/r2-iso.json` (mode 600) and is never committed. `aws-cli` is installed in a venv at
`~/.local/share/meo-aws`; put its `bin` on `PATH` and set `AWS_REQUEST_CHECKSUM_CALCULATION=when_required`
and `AWS_RESPONSE_CHECKSUM_VALIDATION=when_required` (R2 does not accept the newer default checksums).
Rotate the token in R2 > Manage API tokens if it leaks.
