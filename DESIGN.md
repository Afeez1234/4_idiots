---
name: SUAAMS
description: Phone-as-ID class attendance. A dark precision instrument in the hand and on the public site, a light records desk on the web.
colors:
  # Shared across both worlds
  brand-blue: "#2F6BEE"
  # App (Flutter), dark scheme (the default)
  app-midnight: "#0F0F0F"
  app-graphite-card: "#1C1C1C"
  app-graphite-edge: "#2A2A2A"
  app-hairline-dark: "#111111"
  app-text-dark: "#FFFFFF"
  app-text-secondary-dark: "#D4D4D4"
  app-text-muted-dark: "#B0B0B0"
  app-contactless-indigo-dark: "#818CF8"
  app-on-indigo-dark: "#0F0F0F"
  app-present-dark: "#10B981"
  app-present-fill-dark: "#0A1A0A"
  app-present-edge-dark: "#1A3A1A"
  app-late-dark: "#FBBF24"
  app-late-fill-dark: "#1A1408"
  app-late-edge-dark: "#4A3A10"
  app-absent-dark: "#F87171"
  app-absent-fill-dark: "#1A0A0A"
  app-absent-edge-dark: "#4A1515"
  app-error-edge: "#FF5252"
  # App (Flutter), light scheme
  app-paper: "#F4F4F5"
  app-card-light: "#FFFFFF"
  app-edge-light: "#DDDDDD"
  app-hairline-light: "#F0F0F0"
  app-ink: "#1A1A1A"
  app-action-black: "#000000"
  app-text-secondary-light: "#52525B"
  app-text-muted-light: "#6A6A6A"
  app-contactless-indigo-light: "#4F46E5"
  app-on-indigo-light: "#FFFFFF"
  app-present-light: "#065F46"
  app-present-fill-light: "#ECFDF5"
  app-present-edge-light: "#D1FAE5"
  app-late-light: "#92400E"
  app-late-fill-light: "#FFFBEB"
  app-late-edge-light: "#FDE68A"
  app-absent-light: "#991B1B"
  app-absent-fill-light: "#FEF2F2"
  app-absent-edge-light: "#FECACA"
  # Portal (Flask + Tailwind v4), light only
  portal-mist: "#F1F4F8"
  portal-card: "#FFFFFF"
  portal-raised: "#FAFBFD"
  portal-navy-rail: "#14161F"
  portal-navy-rail-hover: "#1E2130"
  portal-hairline: "#E7EAF0"
  portal-divider: "#F1F3F7"
  portal-accent: "#2F6BEE"
  portal-accent-hover: "#1E56CC"
  portal-accent-soft: "#EAF1FE"
  portal-accent-line: "#C7DBFC"
  portal-ink: "#141824"
  portal-secondary: "#5A6474"
  portal-muted: "#646C7D"
  portal-on-rail: "#E8EBF2"
  portal-on-rail-muted: "#7C849A"
  portal-on-rail-line: "#262A38"
  portal-success: "#12A150"
  portal-success-soft: "#E7F6EE"
  portal-success-ink: "#0B7A3B"
  portal-warning: "#C77700"
  portal-warning-soft: "#FDF3E2"
  portal-warning-ink: "#8F5300"
  portal-error: "#D93A3F"
  portal-error-hover: "#B72D32"
  portal-error-soft: "#FCEDED"
  portal-error-ink: "#B42328"
  # Public site (suaams.com.ng: story page, /get, privacy, poster).
  # The site wears the app's world: every colour it shares with the app is
  # the app-* token above. Only values the site adds are listed here.
  site-sunk-dark: "#141414"
  site-sunk-light: "#FAFAFA"
  site-faint-dark: "#8A8A8A"
  site-indigo-hover-dark: "#A5B4FC"
  site-indigo-hover-light: "#4338CA"
  site-indigo-soft-dark: "rgba(129, 140, 248, 0.12)"
  site-indigo-soft-light: "#EEF2FF"
  site-grid-dark: "rgba(255, 255, 255, 0.035)"
  site-grid-light: "rgba(0, 0, 0, 0.04)"
  site-phone-bezel: "#050505"
  site-poster-body: "#3F3F46"
typography:
  app-headline:
    fontFamily: "IBM Plex Sans"
    fontSize: "24sp"
    fontWeight: 700
    letterSpacing: "-0.2"
  app-title-large:
    fontFamily: "IBM Plex Sans"
    fontSize: "20sp"
    fontWeight: 700
    letterSpacing: "-0.2"
  app-title:
    fontFamily: "IBM Plex Sans"
    fontSize: "16sp"
    fontWeight: 600
  app-title-small:
    fontFamily: "IBM Plex Sans"
    fontSize: "14sp"
    fontWeight: 600
  app-body:
    fontFamily: "IBM Plex Sans"
    fontSize: "14sp"
    fontWeight: 400
    lineHeight: 1.45
  app-body-large:
    fontFamily: "IBM Plex Sans"
    fontSize: "16sp"
    fontWeight: 400
    lineHeight: 1.45
  app-body-small:
    fontFamily: "IBM Plex Sans"
    fontSize: "12sp"
    fontWeight: 400
    lineHeight: 1.4
  app-label:
    fontFamily: "IBM Plex Sans"
    fontSize: "12sp"
    fontWeight: 600
    letterSpacing: "0.3"
  app-label-small:
    fontFamily: "IBM Plex Sans"
    fontSize: "11sp"
    fontWeight: 600
    letterSpacing: "0.4"
  app-eyebrow:
    fontFamily: "IBM Plex Sans"
    fontSize: "11sp"
    fontWeight: 600
    letterSpacing: "1.5"
  app-machine:
    fontFamily: "IBM Plex Mono"
    fontWeight: 400
  portal-page-title:
    fontFamily: "Plus Jakarta Sans, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 700
  portal-stat-value:
    fontFamily: "Plus Jakarta Sans, sans-serif"
    fontSize: "1.875rem"
    fontWeight: 800
    lineHeight: 1
  portal-card-title:
    fontFamily: "Plus Jakarta Sans, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 700
  portal-body:
    fontFamily: "Plus Jakarta Sans, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
  portal-label:
    fontFamily: "Plus Jakarta Sans, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    letterSpacing: "0.025em"
  portal-micro:
    fontFamily: "Plus Jakarta Sans, sans-serif"
    fontSize: "11px"
    fontWeight: 600
  portal-mono:
    fontFamily: "JetBrains Mono, monospace"
  site-display:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "clamp(40px, 5vw, 68px)"
    fontWeight: 700
    lineHeight: 1.02
    letterSpacing: "-0.028em"
  site-headline:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "clamp(30px, 3.6vw, 44px)"
    fontWeight: 700
    lineHeight: 1.08
    letterSpacing: "-0.022em"
  site-page-title:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "clamp(36px, 6vw, 56px)"
    fontWeight: 700
    lineHeight: 1.04
    letterSpacing: "-0.022em"
  site-title:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  site-lede:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1.6
  site-body:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.6
  site-caption:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
  site-button:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.2
  site-code:
    fontFamily: "IBM Plex Mono, ui-monospace, monospace"
    fontSize: "clamp(20px, 1.85vw, 28px)"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "0.02em"
  site-count:
    fontFamily: "IBM Plex Mono, ui-monospace, monospace"
    fontSize: "clamp(56px, 6.2vw, 96px)"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.04em"
    fontFeature: "tnum"
  site-readout:
    fontFamily: "IBM Plex Mono, ui-monospace, monospace"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.55
rounded:
  app-sm: "6px"
  app-md: "12px"
  app-lg: "16px"
  portal-btn-sm: "7px"
  portal-btn: "9px"
  portal-card: "14px"
  pill: "9999px"
  site-phone: "40px"
spacing:
  app-xs: "8px"
  app-sm: "12px"
  app-md: "16px"
  app-lg: "20px"
  app-xl: "24px"
  app-2xl: "32px"
  portal-card: "20px"
  portal-page: "28px"
  site-gutter: "clamp(20px, 4.4vw, 64px)"
  site-section: "clamp(72px, 9vw, 120px)"
  site-section-head: "clamp(36px, 4vw, 56px)"
  site-stage-col: "28px"
components:
  app-button-primary-dark:
    backgroundColor: "{colors.app-text-dark}"
    textColor: "{colors.app-action-black}"
    rounded: "{rounded.app-md}"
    height: "56px"
    width: "100%"
  app-button-primary-light:
    backgroundColor: "{colors.app-action-black}"
    textColor: "{colors.app-card-light}"
    rounded: "{rounded.app-md}"
    height: "56px"
    width: "100%"
  app-button-checkin-dark:
    backgroundColor: "{colors.app-contactless-indigo-dark}"
    textColor: "{colors.app-on-indigo-dark}"
    rounded: "{rounded.app-md}"
    height: "56px"
  app-input-dark:
    backgroundColor: "{colors.app-graphite-card}"
    textColor: "{colors.app-text-dark}"
    rounded: "{rounded.app-md}"
    padding: "16px"
  app-input-light:
    backgroundColor: "{colors.app-card-light}"
    textColor: "{colors.app-ink}"
    rounded: "{rounded.app-md}"
    padding: "16px"
  app-card-dark:
    backgroundColor: "{colors.app-graphite-card}"
    rounded: "{rounded.app-md}"
    padding: "16px"
  app-stat-box:
    backgroundColor: "{colors.app-graphite-card}"
    textColor: "{colors.app-text-dark}"
    typography: "{typography.app-title-large}"
    rounded: "{rounded.app-md}"
    padding: "14px 6px"
  app-status-present-dark:
    backgroundColor: "{colors.app-present-fill-dark}"
    textColor: "{colors.app-present-dark}"
    typography: "{typography.app-label-small}"
  app-status-late-dark:
    backgroundColor: "{colors.app-late-fill-dark}"
    textColor: "{colors.app-late-dark}"
    typography: "{typography.app-label-small}"
  app-status-absent-dark:
    backgroundColor: "{colors.app-absent-fill-dark}"
    textColor: "{colors.app-absent-dark}"
    typography: "{typography.app-label-small}"
  app-bottom-nav:
    backgroundColor: "{colors.app-graphite-card}"
    textColor: "{colors.app-contactless-indigo-dark}"
    typography: "{typography.app-label-small}"
    rounded: "{rounded.app-md}"
  portal-button-primary:
    backgroundColor: "{colors.portal-accent}"
    textColor: "{colors.portal-card}"
    typography: "{typography.portal-body}"
    rounded: "{rounded.portal-btn}"
    padding: "10px 16px"
  portal-button-primary-hover:
    backgroundColor: "{colors.portal-accent-hover}"
  portal-button-secondary:
    backgroundColor: "{colors.portal-raised}"
    textColor: "{colors.portal-ink}"
    rounded: "{rounded.portal-btn}"
    padding: "10px 16px"
  portal-button-secondary-hover:
    backgroundColor: "{colors.portal-accent-soft}"
    textColor: "{colors.portal-accent}"
  portal-button-danger:
    backgroundColor: "{colors.portal-error}"
    textColor: "{colors.portal-card}"
    rounded: "{rounded.portal-btn}"
    padding: "10px 16px"
  portal-card:
    backgroundColor: "{colors.portal-card}"
    rounded: "{rounded.portal-card}"
    padding: "{spacing.portal-card}"
  portal-input:
    backgroundColor: "{colors.portal-raised}"
    textColor: "{colors.portal-ink}"
    rounded: "{rounded.portal-btn}"
    padding: "10px 16px"
  portal-nav-link:
    textColor: "{colors.portal-on-rail-muted}"
    rounded: "{rounded.portal-btn}"
    padding: "6px 12px"
  portal-nav-link-active:
    backgroundColor: "{colors.portal-accent}"
    textColor: "{colors.portal-card}"
  portal-pill-success:
    backgroundColor: "{colors.portal-success-soft}"
    textColor: "{colors.portal-success-ink}"
    typography: "{typography.portal-micro}"
    rounded: "{rounded.pill}"
    padding: "2px 8px"
  portal-pill-warning:
    backgroundColor: "{colors.portal-warning-soft}"
    textColor: "{colors.portal-warning-ink}"
    typography: "{typography.portal-micro}"
    rounded: "{rounded.pill}"
    padding: "2px 8px"
  portal-pill-error:
    backgroundColor: "{colors.portal-error-soft}"
    textColor: "{colors.portal-error-ink}"
    typography: "{typography.portal-micro}"
    rounded: "{rounded.pill}"
    padding: "2px 8px"
  portal-chip-course:
    backgroundColor: "{colors.portal-accent-soft}"
    textColor: "{colors.portal-accent}"
    typography: "{typography.portal-micro}"
    rounded: "{rounded.pill}"
    padding: "2px 8px"
  site-button-primary:
    backgroundColor: "{colors.app-contactless-indigo-dark}"
    textColor: "{colors.app-on-indigo-dark}"
    typography: "{typography.site-button}"
    rounded: "{rounded.app-md}"
    height: "52px"
    padding: "0 22px"
  site-button-primary-hover:
    backgroundColor: "{colors.site-indigo-hover-dark}"
  site-button-primary-light:
    backgroundColor: "{colors.app-contactless-indigo-light}"
    textColor: "{colors.app-on-indigo-light}"
  site-button-ghost:
    textColor: "{colors.app-text-dark}"
    typography: "{typography.site-button}"
    rounded: "{rounded.app-md}"
    height: "52px"
    padding: "0 22px"
  site-button-small:
    height: "44px"
    padding: "0 16px"
  site-text-button:
    textColor: "{colors.app-contactless-indigo-dark}"
    height: "44px"
  site-stage-column:
    backgroundColor: "{colors.site-sunk-dark}"
    padding: "{spacing.site-stage-col}"
  site-stage-photo:
    backgroundColor: "{colors.app-graphite-card}"
  site-register-row:
    textColor: "{colors.app-text-muted-dark}"
    typography: "{typography.site-readout}"
    padding: "11px 0"
  site-threat-row:
    textColor: "{colors.app-text-dark}"
    typography: "{typography.site-title}"
    height: "64px"
    padding: "14px 0"
  site-role-row:
    typography: "{typography.site-title}"
    padding: "22px 0"
  site-step-marker:
    textColor: "{colors.app-contactless-indigo-dark}"
    rounded: "{rounded.pill}"
    size: "40px"
  site-prereq-panel:
    backgroundColor: "{colors.app-graphite-card}"
    rounded: "{rounded.app-md}"
    padding: "20px 22px"
  site-warn-note:
    backgroundColor: "{colors.site-indigo-soft-dark}"
    textColor: "{colors.app-text-dark}"
    rounded: "{rounded.app-md}"
    padding: "18px 20px"
  site-install-band:
    backgroundColor: "{colors.app-graphite-card}"
    padding: "clamp(64px, 8vw, 104px) 0"
  site-qr-plate:
    backgroundColor: "{colors.app-card-light}"
    rounded: "{rounded.app-md}"
    size: "168px"
    padding: "10px"
  site-phone-frame:
    backgroundColor: "{colors.site-phone-bezel}"
    rounded: "{rounded.site-phone}"
    width: "min(300px, 78vw)"
    padding: "10px"
  site-poster-sheet:
    backgroundColor: "{colors.app-card-light}"
    textColor: "{colors.app-ink}"
    width: "210mm"
    height: "297mm"
    padding: "18mm 18mm 16mm"
---

# Design System: SUAAMS

<!-- Scope: the Flutter app (SUAAMS_Mobile), the web portal (SUAAMS/templates,
     static/src/input.css), and the public site at suaams.com.ng (landing/:
     the story page index.html + hero.js, the student install page get/, the
     privacy policy privacy.html, all on styles.css; and the printable A4
     poster get/poster.html with its own inline print styles). The site
     lives in the app's world; site-* tokens are only the values it adds. -->

## Overview

**Creative North Star: "Midnight Instrument"**

SUAAMS is a precision tool. In the student's hand it is an instrument on a
black ground: graphite surfaces, white type, a faint measuring grid behind
everything, and one indigo signal, Contactless Indigo, marking the place to
act. Anything a machine says (a time range, a course code, a terminal
status) is set in monospace, so the student can tell at a glance what the
system reports and what the interface just labels. The check-in moment
happens in a queue at a lecture-hall door, so everything on the screen must
be readable in one glance and every control must respond the moment it is
touched.

The system has two worlds that share one set of meanings. The **app** is
dark by default, with a light mode that follows the same rules. The **web
portal** is where admins, lecturers and HODs keep records at a desk. It
uses a light page, white cards and a dark navy sidebar, with a blue accent
for emphasis. The two look different on purpose: one is held in a hand at a
door, the other is worked at a desk all day. They share the brand blue in
the logo, the four attendance status meanings, and the rule that no status
is ever shown by colour alone.

The **public site** at suaams.com.ng is not a third world. It is the app's
Midnight Instrument opened up to page width: the same #0F0F0F ground and
graphite panels, the same Plex pair, the same one indigo signal, and the
same faint 28px measuring grid behind the first screen. Dark is the
default and light follows the visitor's system setting, as in the app, so
the app's own screenshots sit on the page in their native colours. The
only thing that leaves the dark world is the A4 install poster, which is
printed on paper and so is light.

Components are **tactile and confident**: full-width 56dp buttons, 48dp+
tap targets, visible press feedback, and a small scale lift on the active
item. Motion is short (120-280ms, ease-out-cubic) and only confirms a
change. It is never decoration.

**Key Characteristics:**
- App: midnight surfaces (#0F0F0F / #1C1C1C), one indigo accent, IBM Plex Sans + Plex Mono.
- Portal: mist page, white hairline cards, navy rail, one blue accent, Plus Jakarta Sans + JetBrains Mono.
- Status meanings are identical everywhere: present green, late amber, absent red, excused grey. A text label is always shown.
- Every text/surface pair is contrast-measured; values are chosen for AA, not by eye.
- Flat surfaces separated by hairline borders; depth comes from tone, not shadow.
- Site: the app's world at page width. Ruled rows instead of card grids, Plex self-hosted, indigo the one accent, sample data always labelled demo.

## Colors

Mostly monochrome, with two kinds of colour: one accent for action and a
fixed set of status colours for meaning. Every value below comes from code
and was contrast-checked there. Change it in code first, then here.

### Primary
- **Contactless Indigo** (app, dark #818CF8 / light #4F46E5): the app's
  only brand colour. It appears at the same few places every time: the
  active bottom-nav tab, the check-in call to action, the contactless and
  NFC glyphs, the live-session dot. The two values exist because no single
  vivid indigo reads as text on both black and white. Text on it is
  near-black in dark mode and white in light mode, both above 4.5:1.
  On the **site** it is likewise the only accent, with a hover step the app
  doesn't need (#A5B4FC dark, #4338CA light) and a soft tint for the one
  callout note (12% indigo dark, #EEF2FF light). It marks: the primary
  button, links and the "Replay the tap" text button, the focus ring, the
  underline under the code's payload, the leader lines on the stage, the
  live dot, the sequence time markers, the /get step numerals, the privacy
  check marks, and one emphasised phrase in the display headline.
- **Records Blue** (portal, #2F6BEE; hover #1E56CC): the portal's accent.
  It marks the primary button, the active rail link, focus rings, course
  chips and progress fills. Its soft tint (#EAF1FE) and line (#C7DBFC)
  carry hover and selected states.
- **Brand Blue** (#2F6BEE): the dot and NFC arcs in the SUAAMS logo mark,
  on every surface. In the app and on the site it appears only inside the
  logo, never as a UI colour. Contactless Indigo has that job.

### Status (shared meanings, per-world values)
- **Present / success:** green. App text #10B981 dark, #065F46 light. Portal
  fill #12A150, text on tint #0B7A3B.
- **Late / warning:** amber. Late still counts as attended. App text
  #FBBF24 dark, #92400E light. Portal fill #C77700, text on tint #8F5300.
- **Absent / danger:** red. App text #F87171 dark, #991B1B light. Portal
  fill #D93A3F, text on tint #B42328.
- **Excused:** grey, using the world's secondary text colour on a 10% tint.

Each app status is a triple (fill, edge, text); the portal uses fill,
-soft and -ink. Raw saturated hues (#10B981, #F59E0B, #EF4444) are for
icon fills and chart bars only. On a light tint they score 2.0-3.3:1, which
fails as text.

### Neutral
- **Midnight** (#0F0F0F): app dark background. A deliberate choice over
  pure black.
- **Graphite Card** (#1C1C1C): app dark cards, inputs, bottom nav.
- **Graphite Edge** (#2A2A2A): app dark outline.
- **Paper** (#F4F4F5) / **white cards** / **Edge** (#DDDDDD): app light scheme.
- **App text ramp:** dark #FFFFFF / #D4D4D4 / #B0B0B0; light #1A1A1A / #52525B / #6A6A6A.
- **Mist** (#F1F4F8): portal page. **Raised** (#FAFBFD): inputs and secondary
  buttons sitting on the page.
- **Navy Rail** (#14161F, hover #1E2130): the portal sidebar, the one dark
  mass in the light UI. Text on it is #E8EBF2, muted #7C849A, rules #262A38.
- **Portal text ramp:** ink #141824, secondary #5A6474, muted #646C7D.
- **Portal Hairline** (#E7EAF0) and **Divider** (#F1F3F7): card borders and table rules.

**Site neutrals.** The site reuses the app's ground, panel, edge and text
ramp. What it adds:
- **Sunk** (#141414 dark / #FAFAFA light): one step between Midnight and
  Graphite. Only the stage's two side columns sit on it, so the reader
  photo between them reads as the object and IN / OUT read as its readouts.
- **Rules**: hairlines on the page are Graphite Card (#1C1C1C) in dark and
  the app's light Edge (#DDDDDD) in light. Outlined things (ghost buttons,
  panels, the step circles) use Graphite Edge (#2A2A2A) in dark.
- **Faint** (#8A8A8A dark, 5.5:1 on Midnight; the app's light muted
  #6A6A6A in light): captions, the demo label, column labels, the platform
  note. Never body copy. The light scheme's muted body text is the app's
  light secondary (#52525B), not #6A6A6A.
- **Grid** (3.5% white dark, 4% black light): the 28px measuring grid,
  faded out toward the bottom of the first screen.
- **Phone Bezel** (#050505): the frame around the app's screenshots, dark
  in both schemes because the phone is.
- **Poster**: white sheet, ink #1A1A1A, step text #3F3F46, a #DDDDDD rule
  above the footnotes, and the light Contactless Indigo (#4F46E5).

### Named Rules
**The One Signal Rule.** Each world has exactly one accent, and it marks
where to act or where you are. In the app that is Contactless Indigo, and it
always goes on the same few elements so students learn to find it. It never
colours a status value. The site is in the app's world, so its one accent
is Contactless Indigo too; Brand Blue stays inside the logo.

**The Green Is Sacred Rule.** Green means "you're registered." Never spend
it on branding, success toasts for unrelated actions, or decoration. A
student reads green in well under a second, so that meaning must stay
unambiguous. On the site green appears in two places only: the PRESENT
label on the register, and the "75% or more" key that explains the app's
Records colours. Both carry their words.

**The Measured, Not Eyeballed Rule.** Any new text/surface pair is
contrast-checked to WCAG AA (4.5:1 body) before it ships. Status text is
checked against the tinted fill it actually sits on, not the opaque colour.

## Typography

**App UI Font:** IBM Plex Sans (bundled; 400 / 600 / 700)
**App Machine Font:** IBM Plex Mono (bundled; 400)
**Site Fonts:** IBM Plex Sans 400 / 600 / 700 and Plex Mono 400 / 700,
self-hosted WOFF2 cut to Latin (about 70 KB for all five), from the TTFs
the app bundles; `font-display: swap`, Sans Bold and Mono Regular preloaded
**Portal UI Font:** Plus Jakarta Sans (Google Fonts; 400-800)
**Portal Mono Font:** JetBrains Mono

**Character:** Plex is engineered and neutral, a typeface for instruments.
Its mono sibling carries the "terminal" voice without a second design
language. Plus Jakarta Sans on the portal is rounder and friendlier for
long desk sessions.

The app bundles its fonts instead of fetching them at runtime. Slow campus
Wi-Fi must never leave the check-in screen in a fallback face. (CLAUDE.md
still says the app uses Plus Jakarta Sans. That is out of date: the app
ships IBM Plex.) The site follows the same logic for the same audience:
it serves its own Plex files rather than calling Google Fonts, because on
campus Wi-Fi a third-party font request is the slowest thing on the page.

### Hierarchy (app, sp)
- **Headline** (700, 24, -0.2 tracking): the one or two words a screen is about.
- **Title Large** (700, 20, -0.2): section heads, stat values.
- **Title** (600, 16) / **Title Small** (600, 14): card and row titles.
- **Body** (400, 14, 1.45) / **Body Large** (400, 16) / **Body Small** (400, 12, 1.4).
- **Label** (600, 12, +0.3) / **Label Small** (600, 11, +0.4): bottom-nav labels, stat captions.
- **Eyebrow** (600, 11, +1.5, uppercase): the run-in label above a block,
  always paired with a real title.
- **Machine** (Plex Mono 400, inherits size): times, codes, terminal strings.

### Hierarchy (site, px)
The site scale is its own (pages are wider than phones) but the roles map
one to one onto the app's.
- **Display** (700, clamp 40-68, leading 1.02, -0.028em): the story page
  headline only. Three lines at desktop width so the whole stage fits a
  900px-tall screen.
- **Page Title** (700, clamp 36-56, leading 1.04): /get. The privacy
  policy's title runs a touch smaller (clamp 34-48).
- **Headline** (700, clamp 30-44, leading 1.08, -0.022em): section heads.
  Flat 22-24px for headings inside a document (/get blocks and steps,
  privacy sections).
- **Title** (600, 18, leading 1.3): row and block titles (threat rows,
  roles, fallbacks). The first role row is set larger (24) because students
  are most of the people who use SUAAMS.
- **Lede** (400, 18, 1.6) / **Body** (400, 17, 1.6) / **Caption** (400,
  14-14.5): muted ledes, body, demo labels and footnotes.
- **Button** (600, 16, 1.2); small buttons 15.
- **Code** (Plex Mono 400, clamp 20-28, 1.5, +0.02em): the 32-character
  check-in code, payload on one line and signature on the next.
- **Count** (Plex Mono 700, clamp 56-96, leading 1, -0.04em, tabular
  figures): the register's count; its "/ 200" denominator drops to clamp
  20-30, 400, faint.
- **Readout** (Plex Mono 400, 13, 1.55): decoded values, register rows,
  the QR's URL, the build version on /get.

Headings use `text-wrap: balance` and paragraphs `text-wrap: pretty`, so no
line ends on one stranded word. Nothing on the site renders below 12px.

### Hierarchy (portal)
- **Page Title** (700, 18px), **Card Title** (700, 14px), **Stat Value**
  (800, 30px, leading 1), **Body** (400, 14px), **Label / table head** (600,
  12px, uppercase, wide tracking), **Micro** (600, 11px: pills, captions, help).

### Named Rules
**The 11sp Floor Rule.** Nothing in the app renders below 11sp. The only
exception is the numeric count inside the notification badge, a single
glyph inside a pill. Sub-11 text is a bug, not a style.

**The Mono Means Machine Rule.** Monospace is only for data the system
emits (times, session and course codes, terminal states). Never use it for
labels, buttons or prose. On the site that means the check-in code, the
decoded values, times, masked student IDs, the register count, the build
version and the printed URL. Where a machine readout is followed by an
explanation, the explanation drops back to the sans.

**The Theme Scale Rule.** Text styles come from the theme's text scale
(`Theme.of(context).textTheme`, the portal's Tailwind scale). Never
hand-roll a font size per screen. That is how the app once had 15 sizes.

**The Own Fonts Rule.** The app and the site ship their own Plex files. No
Google Fonts or other third-party font host on anything a student opens on
campus Wi-Fi.

## Layout

**App.** One column, phone width, inside the safe area. Screen padding is
24dp (`EdgeInsets.all(24)`). Cards pad 16dp, sometimes 20dp. Gaps between
stacked cards and stat boxes are 12dp. Stats sit in an equal-width row
(`AppStatRow`). The student and lecturer shells use a five-tab bottom
navigation bar. Keyboard handling uses `resizeToAvoidBottomInset` with
`ClampingScrollPhysics`. Never hand-roll inset spacers.

**Portal.** A 240px navy rail on the left (an off-canvas drawer on mobile)
and a scrolling content column capped at 1400px, padded 20px (28px on large
screens). Admin record pages use a "form column left, directory right" grid
(1/3 + 2/3 at `lg`). Cards pad 20px. Tables pad cells 20px x 12-14px.

**Site.** A 1240px column with a fluid gutter (`site-gutter`). The story
page runs as full-width bands separated by hairline rules (section padding
`site-section`, heads capped at 680px), not as a grid of equal cards. Text
and an app screenshot share a two-column split (0.8fr / 1.2fr, flipped for
alternation), and the "how it works" phone stays sticky beside its steps.
Lists of like things are **ruled rows**: a top rule, then one bottom rule
per row (the timed sequence, the threats, the roles, the /get facts).
Reading pages narrow: /get is capped at 720px, the privacy policy at 760px.

Responsive steps: at 1000px the stage drops to two columns with the photo
spanning the top in its own 4:3 box and the leaders hidden; at 900px splits
stack; at 860px the header nav hides and an Install button takes its place;
at 760px the install band's QR hides (it is for a laptop visitor holding a
phone); at 640px the stage goes to one column and bleeds to the screen
edges, primary buttons go full width, and role rows stack.

## Elevation & Depth

Both worlds are **flat**. Depth comes from tone and hairline borders.

The app uses `elevation: 0` everywhere. Cards are one tonal step above the
background (#0F0F0F to #1C1C1C in dark), with an outline border at
10-14% alpha. The background has a faint 28dp grid (3% alpha, 0.4 stroke)
and two large blurred-edge circles: indigo-tinted on dashboards and auth
screens, red-tinted on the change-password screen as a quiet caution
signal. These are static, sized from `MediaQuery.sizeOf`, and isolated
behind a `RepaintBoundary`.

The portal has two shadows, both barely there:
- **Card** (`0 1px 2px rgb(16 24 40 / 0.04), 0 1px 3px rgb(16 24 40 / 0.06)`): every card, under its hairline border.
- **Pop** (`0 8px 24px rgb(16 24 40 / 0.10), 0 2px 6px rgb(16 24 40 / 0.06)`): menus, the skip link, anything floating above the page.

The site is flat too: no box shadows anywhere. Depth is the step from
Midnight to Sunk to Graphite, and hairline rules do the separating. The
only inset shadow is a 2px line used as an underline under the code's
payload (indigo) and signature (edge grey), drawn that way so it follows
the text's own width.

### Named Rules
**The Borders Separate Rule.** Hairline borders do the separating, not
shadows. If a surface needs more distinction, step its tone. Don't deepen
its shadow.

## Shapes

Gently rounded, never pill-soft except where a shape is meant to be a pill.

- **App:** 12dp is the default for buttons, inputs, cards, stat boxes and
  nav tiles. 16dp for larger containers and sheets. 6-8dp for small tags
  and inner elements. Circles for avatars, status dots and the logo's head.
- **Portal:** 14px cards, 9px buttons and inputs, 7px compact buttons, full
  pills for status pills, course chips and tab pills.
- **Site:** the app's 12px for buttons, panels, the callout note and the QR
  plate; 16px for the privacy summary box; 8px for header nav links; 6px
  on the focus ring. The stage, rows and bands have square edges: they are
  ruled, not boxed. Circles for the live dot and the /get step numerals.
  The screenshot phone frame is the one soft shape (40px outer, 31px
  screen), because it is a drawing of a phone.

## Components

### Buttons (app)
Tactile and confident.
- **Shape:** 12dp corners, full width, 56dp tall.
- **Primary:** inverse of the surface: white with black text in dark,
  black with white text in light. Bold 16sp label.
- **Check-in CTA:** Contactless Indigo with on-indigo text. This is the one
  primary action that wears the accent.
- **Loading:** the label becomes a 24dp, 2-stroke spinner. The button is
  disabled while loading.
- **Press:** Material ink splash at 10% of the foreground.

### Buttons (portal)
- **Shape:** 9px corners, 10px x 16px padding, 14px semibold. Compact variant 7px / 6px x 12px / 12px.
- **Primary:** Records Blue, white text, hover to #1E56CC.
- **Secondary:** raised white with a hairline border. Hover tints to accent-soft with blue text.
- **Ghost:** secondary text, hover to the mist page colour.
- **Danger:** error red, white text.
- **Text link** ("Edit", "Unbind"): 12px, dotted underline, 24px minimum hit
  height. Hover turns it red, since these links lead to consequential actions.
- **Disabled:** 40% opacity, no pointer events.

### Status pills
- **App:** a status triple (tinted fill, edge, text) from
  `attendance_status.dart`, with uppercase labels PRESENT / LATE / ABSENT / EXCUSED.
- **Portal:** full pill, 2px x 8px, 11px semibold, `-soft` background with
  `-ink` text, selected by `data-tone` (never an interpolated class name).
- One map per side: `attendanceStatusText` / `attendanceStatusSurface` in
  the app, the `attendance_status_pill` macro on the web. Never hand-write another.

### Cards / Containers
- **App:** graphite (#1C1C1C) or white, 12dp corners, outline at 10% alpha,
  16dp padding. Record rows are 72% surfaceContainer with the same edge.
- **Portal:** white, 14px corners, hairline border, card shadow, 20px body.
  Header row, then body, then a footer separated by a divider rule. Use the
  clipped variant when a table bleeds to the edge.

### Inputs / Fields
- **App:** filled (graphite or white), no border at rest, 12dp corners, 16dp
  padding. Focus adds a 1dp border in the primary colour (white or black).
  Error adds a 1.5dp #FF5252 border. Text fields sit inside a
  `RepaintBoundary` so the blinking cursor doesn't repaint the backdrop.
- **Portal:** raised fill, hairline border, 9px corners. Focus turns the
  border blue and adds a 1px blue ring. Destructive fields focus in red.

### Navigation
- **App bottom nav:** surfaceContainer bar with a top hairline, five equal
  tiles. The active tile gets the accent icon and label, a 10% primary pill
  with a 28% border, and scales from 0.96 to 1.0 over 180ms ease-out-cubic.
  Labels are 11sp, never all-caps. Count badges use the primary colour;
  "something is live" uses an accent dot. Red is reserved for failure.
- **Portal rail:** navy, 240px. Links are muted-on-navy and lighten on
  hover. The active link is filled Records Blue with white text. Section
  labels are 11px uppercase with wide tracking. The scroll edge is marked
  with a fade, not a scrollbar.

### Stat boxes (signature)
A value over a caption, in an equal-width row. Neutral stats sit on a 78%
surfaceContainer with a faint edge. A success or warning stat tints its
box with the status colour at 12% fill and 35% border. Tone is set
explicitly (`AppStatTone`) and is never derived from the label text. The
portal's equivalent is the stat card: an uppercase label, an 800-weight
30px value, and an 11px caption.

### Buttons (site)
- **Shape:** 12px corners, 52px tall, 0 x 22px padding, 16px semibold,
  20px icon. Small variant 44px tall, 15px.
- **Primary:** Contactless Indigo with on-indigo text; hover to the
  lighter (dark) or deeper (light) indigo step.
- **Ghost:** transparent with a Graphite Edge border and white text;
  hover brightens the border to the muted grey.
- **Text button** ("Replay the tap"): indigo, 14px semibold, 16px icon, no
  box, still 44px tall for the tap target.
- **Press:** scale 0.98 over 120ms. Colour transitions 180ms.
- **Focus:** 2px indigo outline, 3px offset, on every focusable element.

### The stage (site signature)
The story page's first screen. A full-width band of three columns between
two hairline rules: **IN** (what the phone sends), the **reader photo**
(about 40% of the width and the tallest thing on screen), and **OUT** (what
the lecturer gets). The side columns sit on Sunk with a hairline toward
the photo; 2px indigo **leader lines** cross from each side column into the
photo at mid-height.
- **IN:** the 32-character code in the Code style, payload on one line
  underlined in indigo, signature on the next underlined in edge grey. A
  short definition list below decodes it: each term is keyed by a 10 x 2px
  bar in the matching underline colour, values in Readout, and the
  explanation of the signature in the sans.
- **OUT:** a live dot in the label, the Count with its denominator, the
  class in the sans, then four ruled register rows (time, masked ID,
  PRESENT in green), the newest in full white and the rest muted.
- **Demo label:** a faint caption under the stage says it is demo data;
  "Replay the tap" sits opposite it.
- **The tap, played once (verify → tap → recorded):** when the stage first
  comes 35% into view, about 1.5s in total, from one Web Animations
  timeline in `hero.js`:
  - *Verify* (deliberate): the "fingerprint verified" line fades and
    scales in from .96 (220ms, ease-out, at 120ms), its indigo check
    follows (160ms, at 380ms).
  - *Tap* (fast): the code arrives whole with a left-to-right clip reveal,
    payload then signature 60ms behind (220ms each, from 540ms); the IN
    leader draws in 180ms with the strong ease-in-out (at 860ms); the photo
    flashes a 2px indigo ring once, the reader's "beep" (300ms, at 960ms).
  - *Recorded* (fast): the OUT leader draws (180ms, at 1040ms); the
    register slides down one 36px row inside a four-row window, the new row
    fading in and the oldest fading out (240 / 200 / 160ms, at 1220ms); the
    count's last digit rolls 6 → 7 (220ms); the live dot blinks once.
  - Slow where the person acts, fast where the system responds: the tap
    leader is the quickest beat because the real exchange is about 0.1s.
  - The markup is the finished state. An inline script in `<head>` adds
    `.motion` before first paint so the stage starts rewound (no flash of
    the finished stage); a 3s fallback (`.motion-done`) shows the finished
    stage if `hero.js` never arrives. With no script at all the finished
    stage is plain markup. Reduced motion plays the same beats as opacity
    fades only (no clip, travel or roll). Replay fades the stage out over
    150ms, then replays.
- **Photo pending:** until the reader photo is uploaded, the centre shows
  a hatched frame naming the shot it is waiting for.

### The hall (site)
The one quiet statement after the stage, and the page's second visual beat:
the stage shows one tap, the hall shows a whole lecture.
- **Layout:** a display-size headline ("A 200-student hall, checked in
  without a queue.", clamp(32px, 4.2vw, 56px)) with the worked-out timings
  and a faint "worked out, not timed with a crowd" note, beside a 20 x 10
  grid of dots, one per student, in Present green (each dot ends as a
  present check-in, keyed "present" under the grid with the count
  "200 / 200" in Readout). Stacks below 900px.
- **Motion (hall.js):** before the trigger the dots sit scattered and grey,
  spilling a little past the grid (a hall arriving). When the grid is 40% in
  view they snap to their seats in reading order, 7ms apart (200 in 1.4s),
  each a 560ms ease-out travel from scale .8 and half opacity, turning green
  in the last third of its travel; the count ticks with the dots. About 2s,
  once. A fixed pseudo-random scatter, so it looks the same on every visit.
- **Never decoration:** every dot is one student. Don't change the number
  of dots without changing the copy, and keep the timings labelled as
  worked out.
- The finished grid is the markup; until hall.js has scattered it the dots
  are hidden under `.motion` (the same 3s fallback as the stage). Reduced
  motion, no IntersectionObserver or no script: the grid simply shows.
  `overflow-x: clip` on the section keeps spilled dots from widening the
  page.

### Ruled rows (site)
- **Timed sequence** ("how it works"): a 112px marker column with the time
  in indigo Readout (`t = 0`, `within 10 s`, `+ 0.1 s`), then a title and
  muted body. The times are the markers; there are no step numbers.
  Beside it, on desktop, the sticky phone shows each step's real screen
  (ID card, "listening for terminal", "attendance verified" with its
  notification), crossfading in 200ms as that step crosses the middle of
  the window (steps.js); the active step's time stays indigo and the others
  go faint. At 900px and below the sticky phone is replaced by a row of
  three small phones (4px bezel, 18px corners), one per step, labelled
  with the step number in indigo Readout, under the section heading;
  nothing switches or dims there.
- **Threat list:** one `<details>` per attempt. The summary row (64px
  minimum) holds the attempt as a title, what stops it in muted text, and a
  plus that rotates 45 degrees to a cross when open (250ms). Hovering turns
  the title indigo. The one open gap is marked by type, not by a tint: a
  small bold "Not stopped yet" label over its title and its "stops it" text
  raised to full white.
- **Role rows:** the role at left (160-260px), what it gets at right
  (60ch). The first row is students, set larger.
- **Facts** (/get): a 180px term column and a muted definition; machine
  values in the row use Readout.

### Install steps (/get)
A numbered list with a 40px hairline circle holding an indigo bold numeral
and a 1px rule running down to the next step. The download button lives
**inside step 1**, under its heading, not above the list. A Graphite panel
before the list says what you need; one indigo-tinted note after it carries
the one-phone warning. Three ruled facts lists follow: what the app asks
for, who makes it, and what to do if something goes wrong.

### Install band (site)
The story page closes on one Graphite band: a headline, a muted line and
the primary install button on the left, and on wide screens a 168px QR on
a white 12px plate with its URL in Readout under it. The QR hides below
760px, where the visitor is already on a phone.

### Install poster (print exception)
`get/poster.html`, one A4 sheet (210 x 297mm, 18mm margins, no print
margin). The only light surface the student-facing world prints. Mark and
wordmark at top, a 62pt headline with "SUAAMS." in light Contactless
Indigo, a 105mm QR with its URL in 22pt Mono, the three install steps in a
row under indigo-ringed numerals, and two footnotes under a rule. It loads
the site's own Plex files. Light because paper is, not as a new theme.

### App screenshots (site)
The app's real screens in a drawn phone frame (Phone Bezel, 10px border
width, 40px outer corner), capped at 300px, with a centred caption that
always says "(demo account)".

### SUAAMS logo mark (signature)
A figure with an NFC signal: white or black body strokes, Brand Blue head
dot and arcs. Drawn by `SuaamsLogo` (CustomPainter) in the app and by one
inline SVG symbol on the site (same geometry as the portal's `suaams_mark`
macro), with the body strokes in `currentColor`. Never recolour the arcs
to the indigo accent.

## Do's and Don'ts

### Do:
- **Do** use Contactless Indigo only on the active tab, the check-in action, contactless glyphs and live dots.
- **Do** pair every status colour with its text label, from the one shared map on each side.
- **Do** read colours from `AppTerminal` / `colorScheme` (app) or the `@theme` tokens (portal). Never retype a hex at a call site.
- **Do** keep app tap targets at 48dp or more, and full-width primary buttons at 56dp tall.
- **Do** set times, codes and terminal strings in the mono face, and everything else in the sans.
- **Do** contrast-check new pairs against the surface they actually sit on, including tinted fills.
- **Do** build site pages from the app's tokens and the `styles.css` custom properties; dark by default, light by `prefers-color-scheme`.
- **Do** label every piece of sample data as demo, next to it: the stage's code and check-ins, and every screenshot caption.
- **Do** separate site lists with ruled rows (hairline top and bottom), not cards.
- **Do** make every site animation finish into the page's static markup, so no script or reduced motion shows the complete state.
- **Do** self-host fonts for anything a student opens (Plex WOFF2, `font-display: swap`).

### Don't:
- **Don't** use green for anything except "present / success".
- **Don't** render app text below 11sp, or hand-roll a `TextStyle` font size outside the theme scale.
- **Don't** use the raw status hues (#10B981, #F59E0B, #EF4444) as text. They are fills only.
- **Don't** add drop shadows to app surfaces. Step the tone instead.
- **Don't** build portal tone classes by string interpolation (`bg-{{ tone }}`). Use `data-tone`.
- **Don't** load Google Fonts or any third-party font on the app or the site.
- **Don't** add a second accent to the site, or use Brand Blue anywhere but the logo mark.
- **Don't** set prose, headings, labels or buttons in Plex Mono on the site; explanations under a readout go back to the sans.
- **Don't** add box shadows to the site. Step from Midnight to Sunk to Graphite instead.
- **Don't** carry the poster's light sheet onto screen pages; it is the print exception.
