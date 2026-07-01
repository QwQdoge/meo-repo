# meo pacman repository

Repository layout:

```text
x86_64/
  meo.db
  meo.db.tar.gz
  *.pkg.tar.zst
```

Publish packages:

```bash
cp meo-ui-runtime-*.pkg.tar.zst x86_64/
cp meo-installer-*.pkg.tar.zst x86_64/
cd x86_64
repo-add meo.db.tar.gz *.pkg.tar.zst
cd ..
git add .
git commit -m "Publish pacman packages"
git push
```

Pacman config:

```ini
[meo]
SigLevel = Optional TrustAll
Server = https://QwQdoge.github.io/meo-repo/x86_64
```
