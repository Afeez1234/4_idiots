---
version: 1
slug: "landing-index-html"
primary_target: "landing/index.html"
related_targets: ["landing/get/index.html","landing/get/poster.html","landing/privacy.html"]
---

# Surface brief: suaams.com.ng (story page) + /get (install)

Mode: Persuade (both). Plain HTML/CSS, no build step, deployed to Netlify by drag-and-drop (domain DNS at WhoGoHost).

## Audience and job
- `/`: capstone panel, lecturers, HODs sent the link; students who land here need one obvious path to /get.
- `/get`: students sent by a lecturer (QR code in class, or from `/`), on Android, slow campus Wi-Fi or mobile data. Success: installed and signed in at the first try.

## Proof and content
- Reader photo (user supplies: phone mid-tap, reader screen showing class + count, demo account, landscape, >=1600px). Placeholder until then.
- Real-format 32-character demo code (labelled demo, under Security), decoded: payload 16 chars (student, session, expiry) + signature 16 chars.
- The app's real screens for each beat (demo account) and the reader's OLED drawn from the firmware.
- Register, 187/200, labelled demo, masked IDs (under Lecturers).
- Measured figures only: 0.1 s exchange, 10 s expiry, ~4 cm range. App screenshots: the three beat screens in the tap; Records in "Know where you stand".
- /get trust block: version, size, date, SHA-256, signing-cert fingerprint (user supplies; marked pending), permissions from AndroidManifest with reasons (location only Android 11 and older, for Bluetooth scanning), publisher.

## Direction contract
THESIS: The tap is two screens a student already knows, their phone and the reader at the door, changing together in three plain beats. Revised 2026-10-25 from "the reader is the stage" (IN code | reader | OUT register): visitors, nearly all on phones, couldn't read the code or the register, and the stage was a screen and a half of data at 390px. Refuses the split hero of copy beside a phone mockup over a row of equal cards; refuses machine output as the first thing a student is asked to read.
OWN-WORLD: Midnight Instrument from DESIGN.md: #0F0F0F ground, #1C1C1C graphite panels, hairline #2A2A2A edges, white Plex Sans, Plex Mono only for machine output (the code, times, masked IDs, readouts), Contactless Indigo as the one accent (code payload underline, leader lines, primary action, live dot), status green only for PRESENT with its label, faint 28px grid. Light scheme mirrors the app's light tokens.
STORY: A visitor watches their own kind of phone and the reader at the door go from "Check in" / "TAP your phone" to "Attendance verified" / DONE in three beats they can say back, believes a friend can't fake it without the phone, the fingerprint or PIN, and the student's own help (the open gap is named, not hidden), and either installs (student) or reads how it works (evaluator).
FIRST VIEWPORT: Top band: headline left ("Tap your phone at the door. You're marked present."), primary "I'm a student: install the app" (to /get) and ghost "How it works" right. Below, the tap: the phone (real screens) and the reader's drawn OLED side by side, three numbered beats beside them (desktop) or under them (phones), fitting one phone screen at 390px. Demo label under the tap.
FORM: Third on my ordered list after the steer re-roll (reader as the stage), assigned lead. seed:ee1f29b3bb0228e9. Signature interaction: confirm, tap, marked, played once when the beats are in view (phone and reader change screens together, the reader's bezel beeps indigo on the tap, each beat lights as it happens), with a "Replay the tap" text button; reduced motion keeps the screen changes as fades. Timings in DESIGN.md, "The tap".
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Open decisions (user supplies)
- Reader photo; release APK (or SHA-256, size, date) and signing-cert fingerprint; HTTPS live before the QR goes out; whether a public docs/architecture link exists for evaluators.
