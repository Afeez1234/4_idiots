# Landing page — suaams.com.ng

Plain HTML and CSS, no build step. Hosted on WhoGoHost (cPanel), separate
from the Flask server at `portal.suaams.com.ng`. See section 11 of
[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).

| File | What it is |
|---|---|
| `index.html` | The page |
| `privacy.html` | Privacy policy (needed for the Play Store) |
| `styles.css` | All styling; dark by default, light follows the system |
| `favicon.svg` | Tab icon, the SUAAMS mark |
| `.htaccess` | APK download type, caching, www and HTTPS redirects |
| `downloads/` | The APKs. Uploaded to the server only, never committed |

## Publishing

1. cPanel → **File Manager** → `public_html`. Delete the host's
   placeholder page if there is one.
2. Upload `index.html`, `privacy.html`, `styles.css`, `favicon.svg` and
   `.htaccess` (turn on *Show Hidden Files* to see `.htaccess`).
3. Create `public_html/downloads/` and upload the APKs there (below).

### HTTPS

cPanel → **SSL/TLS Status** → *Run AutoSSL* for `suaams.com.ng` and
`www.suaams.com.ng`. Once https://suaams.com.ng opens without a warning,
uncomment the two HTTPS lines at the bottom of `.htaccess`.

## Screenshots

Take them from a **demo student account** (create one in the admin
dashboard), never a real student's: the page is public and the privacy
policy promises not to share student data.

With the phone on USB and the screen open, from the repo root:

```
python landing/tools/shots.py id-card
python landing/tools/shots.py records --from shot.jpg   # a screenshot you already have
```

It crops the status and gesture bars, trims to the phone frame's shape and
writes a ~20 KB WebP to `img/`. The crop defaults suit a Galaxy S24; pass
`--top` / `--bottom` for another phone.

| File | Screen | Used in |
|---|---|---|
| `img/app-id-card.webp` | ID Card tab | Hero |
| `img/app-records.webp` | Records tab | "In the app" section |

Upload into `public_html/img/`. Until a file is there, its phone frame
shows a placeholder label instead of a broken image.

## Releasing a new app build

The universal release APK is ~120 MB because it carries code for every
phone type. Build one per type instead:

```
flutter build apk --release --split-per-abi
```

From `build/app/outputs/flutter-apk/`, upload and rename:

| Built file | Upload as | For |
|---|---|---|
| `app-arm64-v8a-release.apk` | `downloads/suaams-arm64.apk` | Nearly every phone from the last several years |
| `app-armeabi-v7a-release.apk` | `downloads/suaams-armv7.apk` | Older and budget 32-bit phones |

Then update the version line in `index.html` (`Version 0.1.0 · test build`)
to match `pubspec.yaml`.

Always build with the release signing key. A build signed with any other
key can't install over the existing app, and changing the key gives every
phone a new device ID (see CLAUDE.md).

## Content rules

- Every claim must be true of the shipped system. Check the README and
  docs before adding one. The numbers (code lifetime, Bluetooth rotation,
  late cut-off, colour thresholds) are pinned to the code by
  `SUAAMS/tests/test_landing_claims.py`; a new number on the page gets a
  row there.
- No institution's name, logo or crest without written permission.
- Change `privacy.html` (and its date) whenever the app starts collecting
  something new.
