# Landing page — suaams.com.ng

Plain HTML and CSS, no build step. Hosted on Netlify (free plan, deployed
by drag-and-drop); the domain stays registered at WhoGoHost, separate
from the Flask server at `portal.suaams.com.ng`. See section 11 of
[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).

| File | What it is |
|---|---|
| `index.html` | The story page: the reader "stage", how it works, security, privacy |
| `get/index.html` | The student install page, `suaams.com.ng/get` (QR codes point here) |
| `get/poster.html` | Printable A4 poster with the QR code (print from the browser, A4, no margins) |
| `privacy.html` | Privacy policy (needed for the Play Store) |
| `styles.css` | All styling for the three pages; dark by default, light follows the system |
| `hero.js` | The one animation: the tap (verify, tap, recorded) when the stage comes into view, with "Replay the tap"; also hides missing images. Motion timings are in DESIGN.md, "The stage" |
| `hall.js` | The hall: 200 dots, one per student, snapping from a scatter into the register when the section comes into view |
| `steps.js` | "How it works": on desktop the phone beside the steps shows each step's screen as that step reaches the middle of the window (narrow screens show all three in a row instead, no script needed) |
| `fonts/` | IBM Plex Sans and Mono, cut down to Latin WOFF2 from the app's own TTFs |
| `img/qr-get.svg` | QR code for `https://suaams.com.ng/get` |
| `favicon.svg` | Tab icon, the SUAAMS mark |
| `_headers` | Netlify response headers: APKs download as Android installers; two security headers |
| `downloads/` | The APKs. Added to the deploy folder only, never committed |

## Publishing (Netlify)

The domain is registered at WhoGoHost but has no hosting plan there: the
site is on Netlify's free plan. `portal.suaams.com.ng` (Render) is a
separate DNS record and isn't affected by any of this.

### Each deploy

1. Make a deploy folder: everything in `landing/` **except** `README.md`,
   `tools/`, `.gitignore` and the `img/*.json` provenance notes, plus
   `downloads/` with the two APKs (see "Releasing a new app build").
2. Netlify → the site → **Deploys** → drag the folder onto the drop area.
   Each drop replaces the whole site, so always drop the full folder,
   APKs included.

### First-time setup (done once)

1. Sign up at netlify.com, then drag the deploy folder onto
   app.netlify.com/drop. Rename the site (Site configuration → Change site
   name) to something like `suaams`, giving `suaams.netlify.app`.
2. Domain management → **Add a domain** → `suaams.com.ng`. Choose
   **external DNS** (keep DNS at WhoGoHost), and keep `suaams.com.ng` as the
   **primary domain**: the QR code, canonical links and poster use it, and
   `www` then redirects to it.
3. WhoGoHost → DNS Management → `suaams.com.ng`:
   - `A` record, host `@`, value `75.2.60.5` (remove any other `@` A
     record, e.g. a parking page);
   - `CNAME` record, host `www`, value `suaams.netlify.app`;
   - leave the `portal` CNAME (Render) exactly as it is.
4. Once DNS has spread (minutes to a day), Netlify issues the HTTPS
   certificate by itself; turn on **Force HTTPS** under Domain management
   → HTTPS if it isn't already on.

## Screenshots

Take them from a **demo student account** (create one in the admin
dashboard), never a real student's: the page is public and the privacy
policy promises not to share student data.

With the phone on USB and the screen open, from the repo root:

```
python landing/tools/shots.py id-card
python landing/tools/shots.py records --from shot.jpg   # a screenshot you already have
```

Android won't screenshot the fingerprint prompt (it comes out black), so step one uses the ID card's Check in button instead. With `--from`, pass `--top 120 --bottom 50` (Galaxy S24) yourself: the crop is off by default there, and the status bar shows your own notification icons.

It crops the status and gesture bars, trims to the phone frame's shape and
writes a ~20 KB WebP to `img/`. The crop defaults suit a Galaxy S24; pass
`--top` / `--bottom` for another phone.

| File | Screen | Used in |
|---|---|---|
| `img/app-id-card.webp` | ID Card tab | "How it works", step one |
| `img/app-records.webp` | Records tab | "Know where you stand" |
| `img/app-tap.webp` | "Listening for terminal" sheet, mid check-in | "How it works", step two |
| `img/app-marked.webp` | "Attendance verified" sheet with the "Attendance recorded" notification | "How it works", step three |

Upload into `public_html/img/`. Until a file is there, its phone frame
shows a placeholder label instead of a broken image.

### The reader photo

The first screen's centre is a photo of the reader in use:
`img/reader-tap.webp`, landscape, about 1600 x 1200. A phone mid-tap on
the reader, the reader's screen showing the class and the live count,
from a demo account. Until it's uploaded, a "Reader photo coming" frame
shows. Don't publish the site to students with that frame still showing.

### The QR code

`img/qr-get.svg` encodes `https://suaams.com.ng/get` and never needs
regenerating: new app versions change the page behind it, not the code.
To regenerate anyway: `pip install segno`, then
`segno.make('https://suaams.com.ng/get', error='m').save('qr-get.svg',
border=2, dark='#0F0F0F')`, and put the `viewBox="0 0 29 29"` back on
the `<svg>` tag so it scales. Print the poster or show the QR only once
HTTPS works **and** both APKs are in `public_html/downloads/`: until then
the code leads to a page whose Download button 404s.

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

Then, in `get/index.html`:

- update the version line (`Version 0.1.0 · test build`) to match
  `pubspec.yaml`, and add the size and date;
- add the two commented checksum rows under "Who makes it": the APK's
  SHA-256 (`certutil -hashfile suaams-arm64.apk SHA256` on Windows) and
  the signing certificate's SHA-256 (`keytool -printcert -jarfile
  suaams-arm64.apk`).

Always build with the release signing key. A build signed with any other
key can't install over the existing app, and changing the key gives every
phone a new device ID (see CLAUDE.md).

Split builds number themselves 1000 x phone type + build: build 2 is 1002
(armv7) and 2002 (arm64). The server strips that for the update gate
(`SUAAMS/app_version.py`), but Android doesn't: it refuses to install a
lower number over a higher one. So:

- **Publish split APKs only.** A phone on 2002 can't take a universal
  build (2, or 3 later) over it.
- **Keep the pubspec build number below 1000.**
- **Moving to the Play Store:** upload an App Bundle (Play splits it, with
  no offset) and set the build number above 2002 first, e.g.
  `version: 1.0.0+3000`, so Play can update phones that installed from
  here.

## Content rules

- Every claim must be true of the shipped system. Check the README and
  docs before adding one. The numbers (code lifetime, Bluetooth rotation,
  late cut-off, colour thresholds) are pinned to the code by
  `SUAAMS/tests/test_landing_claims.py`; a new number on the page gets a
  row there. The test also checks the demo check-in code keeps the real
  16 + 16 character shape, and that `get/index.html`'s permission list
  matches the AndroidManifest.
- Demo data (the code and check-ins on the first screen) stays labelled
  as demo.
- No institution's name, logo or crest without written permission.
- Change `privacy.html` (and its date) whenever the app starts collecting
  something new.
