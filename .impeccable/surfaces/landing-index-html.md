---
version: 1
slug: "landing-index-html"
primary_target: "landing/index.html"
related_targets: ["landing/get/index.html","landing/get/poster.html","landing/privacy.html"]
---

# Surface brief: suaams.com.ng (story page) + /get (install)

Mode: Persuade (both). Plain HTML/CSS, no build step, hand-uploaded to WhoGoHost.

## Audience and job
- `/`: capstone panel, lecturers, HODs sent the link; students who land here need one obvious path to /get.
- `/get`: students sent by a lecturer (QR code in class, or from `/`), on Android, slow campus Wi-Fi or mobile data. Success: installed and signed in at the first try.

## Proof and content
- Reader photo (user supplies: phone mid-tap, reader screen showing class + count, demo account, landscape, >=1600px). Placeholder until then.
- Real-format 32-character demo code (labelled demo), decoded: payload 16 chars (student, session, expiry) + signature 16 chars.
- Register filling, 187/200, labelled demo, masked IDs.
- Measured figures only: 0.1 s exchange, 10 s expiry, ~4 cm range. App screenshots below the fold: ID card beside How it works step 1; Records in "Know where you stand".
- /get trust block: version, size, date, SHA-256, signing-cert fingerprint (user supplies; marked pending), permissions from AndroidManifest with reasons (location only Android 11 and older, for Bluetooth scanning), publisher.

## Direction contract
THESIS: The reader is the stage: what goes into it (the decoded code) and what comes out (the register) flank the photo of the tap. Refuses the split hero of copy beside a phone mockup over a row of equal cards.
OWN-WORLD: Midnight Instrument from DESIGN.md: #0F0F0F ground, #1C1C1C graphite panels, hairline #2A2A2A edges, white Plex Sans, Plex Mono only for machine output (the code, times, masked IDs, readouts), Contactless Indigo as the one accent (code payload underline, leader lines, primary action, live dot), status green only for PRESENT with its label, faint 28px grid. Light scheme mirrors the app's light tokens.
STORY: A visitor sees a phone tap a real reader, reads the 32 characters it sent and what they mean, watches the register tick to 187, believes a friend can't fake it without the phone and fingerprint or PIN, and either installs (student) or reads how it works (evaluator).
FIRST VIEWPORT: Top band: headline left ("Tap your phone at the door. You're marked present."), primary "I'm a student: install the app" (to /get) and ghost "How it works" right. Below, a full-width three-column stage: IN (mono code, payload and signature underlined, two decoded lines), centre reader photo (about 40% width, tallest element), OUT (count 187 / 200 large mono, class line, four newest log lines). Indigo leaders join IN to photo and photo to OUT. Demo label under the stage.
FORM: Third on my ordered list after the steer re-roll (reader as the stage), assigned lead. seed:ee1f29b3bb0228e9. Signature interaction: verify, tap, recorded, played once when the stage comes into view (fingerprint verified, the signed code clips in whole, leader to the reader with an indigo beep, leader to the register, row slides down, last digit rolls 186 to 187), with a "Replay the tap" text button; reduced motion plays the beats as fades only. Timings in DESIGN.md, "The stage".
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Open decisions (user supplies)
- Reader photo; release APK (or SHA-256, size, date) and signing-cert fingerprint; HTTPS live before the QR goes out; whether a public docs/architecture link exists for evaluators.
