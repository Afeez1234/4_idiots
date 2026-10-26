---
name: SUAAMS
description: Phone-as-ID class attendance. A dark precision instrument in the hand and on the public site, the same instrument in light at the records desk.
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
  # Portal (Flask + Tailwind v4), light only. The portal wears the app's
  # world in light: every colour it shares with the app or the site is that
  # token (Midnight rail, Graphite hover, white panels, ink, secondary text,
  # light Contactless Indigo and its hover and soft steps, the rail's muted
  # text). Only values the portal adds are listed here.
  portal-paper: "#E9EBF6"
  portal-raised: "#F7F8FC"
  portal-hairline: "#D6D9EA"
  portal-divider: "#E8EAF4"
  portal-topbar: "#DCE0F6"
  portal-topbar-line: "#C7CDEC"
  portal-topbar-ink: "#3F3F6B"
  portal-indigo-line: "#C7D2FE"
  portal-muted: "#62626C"
  portal-on-rail: "#E5E5E5"
  portal-grid: "rgba(79, 70, 229, 0.07)"
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
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 700
    letterSpacing: "-0.025em"
  portal-card-title:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 700
  portal-body:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
  portal-micro:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 600
  portal-column-label:
    fontFamily: "IBM Plex Mono, ui-monospace, Consolas, monospace"
    fontSize: "11px"
    fontWeight: 400
    letterSpacing: "0.1em"
  portal-figure:
    fontFamily: "IBM Plex Mono, ui-monospace, Consolas, monospace"
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.25
    fontFeature: "tnum"
  portal-stat-value:
    fontFamily: "IBM Plex Mono, ui-monospace, Consolas, monospace"
    fontSize: "1.875rem"
    fontWeight: 700
    lineHeight: 1
    fontFeature: "tnum"
  portal-board-time:
    fontFamily: "IBM Plex Mono, ui-monospace, Consolas, monospace"
    fontSize: "15px"
    fontWeight: 700
    fontFeature: "tnum"
  portal-reader:
    fontFamily: "IBM Plex Mono, ui-monospace, Consolas, monospace"
    fontSize: "11.5px"
    fontWeight: 400
    lineHeight: 1.375
    letterSpacing: "0.025em"
  portal-mono:
    fontFamily: "IBM Plex Mono, ui-monospace, Consolas, monospace"
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
    fontSize: "clamp(19px, 2vw, 26px)"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "0.02em"
  site-count:
    fontFamily: "IBM Plex Mono, ui-monospace, monospace"
    fontSize: "28px"
    fontWeight: 700
    lineHeight: 1
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
  portal-btn: "8px"
  portal-nav: "9px"
  portal-card: "12px"
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
  portal-grid: "28px"
  site-gutter: "clamp(20px, 4.4vw, 64px)"
  site-section: "clamp(72px, 9vw, 120px)"
  site-section-head: "clamp(36px, 4vw, 56px)"
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
    backgroundColor: "{colors.app-contactless-indigo-light}"
    textColor: "{colors.app-card-light}"
    typography: "{typography.portal-body}"
    rounded: "{rounded.portal-btn}"
    padding: "10px 16px"
  portal-button-primary-hover:
    backgroundColor: "{colors.site-indigo-hover-light}"
  portal-button-secondary:
    backgroundColor: "{colors.portal-raised}"
    textColor: "{colors.app-ink}"
    rounded: "{rounded.portal-btn}"
    padding: "10px 16px"
  portal-button-secondary-hover:
    backgroundColor: "{colors.site-indigo-soft-light}"
    textColor: "{colors.app-contactless-indigo-light}"
  portal-button-danger:
    backgroundColor: "{colors.portal-error}"
    textColor: "{colors.app-card-light}"
    rounded: "{rounded.portal-btn}"
    padding: "10px 16px"
  portal-button-danger-hover:
    backgroundColor: "{colors.portal-error-hover}"
  portal-card:
    backgroundColor: "{colors.app-card-light}"
    rounded: "{rounded.portal-card}"
    padding: "{spacing.portal-card}"
  portal-input:
    backgroundColor: "{colors.portal-raised}"
    textColor: "{colors.app-ink}"
    rounded: "{rounded.portal-btn}"
    padding: "10px 16px"
  portal-topbar:
    backgroundColor: "{colors.portal-topbar}"
    textColor: "{colors.portal-topbar-ink}"
    height: "56px"
  portal-find:
    backgroundColor: "{colors.app-card-light}"
    textColor: "{colors.app-ink}"
    rounded: "{rounded.portal-btn}"
    height: "36px"
    width: "460px"
  portal-rail:
    backgroundColor: "{colors.app-midnight}"
    textColor: "{colors.portal-on-rail}"
    width: "232px"
  portal-nav-link:
    textColor: "{colors.site-faint-dark}"
    rounded: "{rounded.portal-nav}"
    padding: "6px 12px"
  portal-nav-link-active:
    backgroundColor: "{colors.app-graphite-card}"
    textColor: "{colors.app-text-dark}"
  portal-nav-badge:
    backgroundColor: "{colors.app-contactless-indigo-light}"
    textColor: "{colors.app-card-light}"
    typography: "{typography.portal-column-label}"
    rounded: "{rounded.pill}"
    height: "20px"
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
  portal-pill-neutral:
    backgroundColor: "{colors.portal-paper}"
    textColor: "{colors.app-text-secondary-light}"
    typography: "{typography.portal-micro}"
    rounded: "{rounded.pill}"
    padding: "2px 8px"
  portal-pill-live:
    backgroundColor: "{colors.site-indigo-soft-light}"
    textColor: "{colors.site-indigo-hover-light}"
    typography: "{typography.portal-micro}"
    rounded: "{rounded.pill}"
    padding: "2px 8px"
  portal-pill-ink:
    backgroundColor: "{colors.app-ink}"
    textColor: "{colors.app-card-light}"
    typography: "{typography.portal-micro}"
    rounded: "{rounded.pill}"
    padding: "2px 8px"
  portal-facts:
    backgroundColor: "{colors.app-card-light}"
    textColor: "{colors.portal-muted}"
    typography: "{typography.portal-figure}"
    rounded: "{rounded.portal-card}"
    padding: "10px 16px"
  portal-board:
    backgroundColor: "{colors.app-card-light}"
    rounded: "{rounded.portal-card}"
  portal-board-group-needs:
    backgroundColor: "{colors.site-indigo-soft-light}"
    textColor: "{colors.site-indigo-hover-light}"
    typography: "{typography.portal-column-label}"
    height: "32px"
  portal-reader-lit:
    backgroundColor: "{colors.app-midnight}"
    textColor: "{colors.portal-on-rail}"
    typography: "{typography.portal-reader}"
    rounded: "{rounded.portal-btn-sm}"
    padding: "4px 10px"
  portal-reader-dim:
    backgroundColor: "{colors.portal-raised}"
    textColor: "{colors.portal-muted}"
    typography: "{typography.portal-reader}"
    rounded: "{rounded.portal-btn-sm}"
    padding: "4px 10px"
  portal-reader-off:
    backgroundColor: "{colors.app-card-light}"
    textColor: "{colors.app-ink}"
    typography: "{typography.portal-reader}"
    rounded: "{rounded.portal-btn-sm}"
    padding: "4px 10px"
  portal-drawer:
    backgroundColor: "{colors.app-card-light}"
    textColor: "{colors.app-ink}"
    width: "400px"
  portal-drawer-avatar:
    backgroundColor: "{colors.app-midnight}"
    textColor: "{colors.app-text-dark}"
    rounded: "10px"
    size: "44px"
  portal-modal:
    backgroundColor: "{colors.app-card-light}"
    textColor: "{colors.app-ink}"
    rounded: "{rounded.portal-card}"
    padding: "24px"
    width: "448px"
  portal-reveal:
    backgroundColor: "{colors.site-indigo-soft-light}"
    rounded: "{rounded.portal-card}"
    padding: "12px 16px"
  portal-reveal-secret:
    backgroundColor: "{colors.app-midnight}"
    textColor: "{colors.app-text-dark}"
    rounded: "{rounded.portal-btn}"
    padding: "6px 12px"
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
  site-tap-reader:
    backgroundColor: "{colors.site-phone-bezel}"
    rounded: "10px"
    padding: "10px"
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
     static/src/input.css, icons.py; rebuilt 2026-10-25), and the public site at suaams.com.ng (landing/:
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

The **app** is dark by default, with a light mode that follows the same
rules. The **web portal** is where admins, lecturers and HODs keep records
at a desk, and since 2026-10-25 it is the app's Midnight Instrument in
light, at desk width: a Midnight rail (the app's own #0F0F0F ground), an
indigo-tinted Paper page under a soft indigo top bar, white panels on cool
hairlines, the same Plex pair, and the same one indigo signal. A faint 28px
measuring grid sits behind every page head. Its home screen is the door
board, one row per class today, each showing what that room's reader is
showing in the firmware's own words. It replaced a navy rail, mist page and
Records Blue accent that read as a generic admin kit and shared nothing with
the app. Every surface shares the brand blue in the logo, the four
attendance status meanings, and the rule that no status is ever shown by
colour alone.

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
- Portal: the app's world in light. Midnight rail, indigo-tinted Paper page and top bar, white hairline panels, Contactless Indigo the one signal, IBM Plex self-hosted, Lucide icons inlined as SVG.
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
  underline under the code's payload, the reader's "beep" ring and the
  lit beat numbers on the tap, the live dot, the sequence time markers, the /get step numerals, the privacy
  check marks, and one emphasised phrase in the display headline.
  On the **portal** it is the light value (6.3:1 on white, white on it
  6.3:1), with the site's light hover step, its soft tint, and a line
  (#C7D2FE) for borders on the tint. Indigo text on the soft tint uses the
  hover step (7.07:1). It marks: the primary button, the active rail link's
  2px left edge, the active tab pill, the focus ring, the text caret and the
  Find field's focus border, the door board's Needs you band and the "need
  you" figure, the nav count badge, live pills, NFC as a check-in method,
  info alerts, and the one-time password panel. On a lit reader screen
  (Midnight) the live dot takes the dark value (#818CF8) instead.
- **Brand Blue** (#2F6BEE): the dot and NFC arcs in the SUAAMS logo mark,
  on every surface. It appears only inside the logo, never as a UI colour.
  Contactless Indigo has that job.

### Status (shared meanings, per-world values)
- **Present / success:** green. App text #10B981 dark, #065F46 light. Portal
  fill #12A150, text on tint #0B7A3B.
- **Late / warning:** amber. Late still counts as attended. App text
  #FBBF24 dark, #92400E light. Portal fill #C77700, text on tint #8F5300.
- **Absent / danger:** red. App text #F87171 dark, #991B1B light. Portal
  fill #D93A3F, text on tint #B42328.
- **Excused:** grey, using the world's secondary text colour on a 10% tint
  (portal: secondary text on the Paper tint, the neutral pill).

**Operational states (portal).** Machine and lifecycle states never borrow
an attendance colour. An ordinary state (Active, Pending setup, Ended,
Not started yet) is the neutral pill. "Needs you" and "live" are indigo. A
state that should stand out without meaning attendance (a reader or sign-in
switched off, a disabled reader, an invalid level in an upload, an expelled
or deceased record) is the solid ink pill: #1A1A1A with white text.

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

**Portal neutrals.** The portal reuses the app's Midnight, Graphite, white
panels and light text ramp. What it adds:
- **Midnight Rail**: the sidebar is the app's own ground (#0F0F0F), with
  Graphite (#1C1C1C) for hover and the active link. Text on it is #E5E5E5
  (15.2:1), muted the site's Faint #8A8A8A (5.5:1 on Midnight, 4.9:1 on
  Graphite), rules Graphite Edge (#2A2A2A).
- **Indigo Paper** (#E9EBF6): the page, the app's Paper tinted toward
  indigo. **Raised** (#F7F8FC): inputs, secondary buttons, table heads, the
  board's column and group bands, the drawer's action bar.
- **Top Bar** (#DCE0F6, rule #C7CDEC, text #3F3F6B at 7.5:1): one step
  deeper than the page.
- **Portal text ramp:** ink #1A1A1A (14.7:1 on the page), secondary
  #52525B (6.5:1 on the page, 5.9:1 on the top bar), muted #62626C (5.1:1
  on the page, 6.0:1 on a panel, 4.6:1 on the top bar). Muted is not the
  app's #6A6A6A, which measured 4.55:1 on the tinted page.
- **Portal Hairline** (#D6D9EA), cooled to sit on the tint, and **Divider**
  (#E8EAF4): panel borders, and inner rules and table row lines.
- **Grid** (7% indigo): the 28px measuring grid behind page heads.

**Site neutrals.** The site reuses the app's ground, panel, edge and text
ramp. What it adds:
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
**The One Signal Rule.** Each surface has exactly one accent, and it marks
where to act or where you are. In the app that is Contactless Indigo, and it
always goes on the same few elements so students learn to find it. It never
colours a status value. The site and the portal are in the app's world, so
their one accent is Contactless Indigo too (the portal uses the light
value); Brand Blue stays inside the logo. In the portal indigo means act
here, you are here, needs you, or live. It is never a record's status.

**The Green Is Sacred Rule.** Green means "you're registered." Never spend
it on branding, success toasts for unrelated actions, or decoration. A
student reads green in well under a second, so that meaning must stay
unambiguous. On the site green appears in two places only: the PRESENT
label on the register, and the "75% or more" key that explains the app's
Records colours. Both carry their words. In the portal green is attendance
only: a present status, an attendance rate at or above 75%, and the fill of
a course's exam standing bar. A live class is indigo, a lifecycle state is
neutral or the ink pill, and amber stays "late" or "below 75%", so a
check-in method or a draft count never wears it.

**The Measured, Not Eyeballed Rule.** Any new text/surface pair is
contrast-checked to WCAG AA (4.5:1 body) before it ships. Status text is
checked against the tinted fill it actually sits on, not the opaque colour.

## Typography

**App UI Font:** IBM Plex Sans (bundled; 400 / 600 / 700)
**App Machine Font:** IBM Plex Mono (bundled; 400)
**Site Fonts:** IBM Plex Sans 400 / 600 / 700 and Plex Mono 400 / 700,
self-hosted WOFF2 cut to Latin (about 70 KB for all five), from the TTFs
the app bundles; `font-display: swap`, Sans Bold and Mono Regular preloaded
**Portal Fonts:** IBM Plex Sans 400 / 600 / 700 and Plex Mono 400 / 700,
self-hosted WOFF2 from the portal's static fonts (the same files as the app
and the site); `font-display: swap`, Sans Regular and SemiBold preloaded.
Icons are Lucide, inlined as SVG (2px stroke, `currentColor`) by
`icons.py`; there is no icon font.

**Character:** Plex is engineered and neutral, a typeface for instruments.
Its mono sibling carries the "terminal" voice without a second design
language. The portal uses the same pair, so a course code or a time reads
the same on a phone, on a reader's screen and at a desk.

The app bundles its fonts instead of fetching them at runtime. Slow campus
Wi-Fi must never leave the check-in screen in a fallback face. (CLAUDE.md
still says the app uses Plus Jakarta Sans. That is out of date: the app
ships IBM Plex.) The site follows the same logic for the same audience:
it serves its own Plex files rather than calling Google Fonts, because on
campus Wi-Fi a third-party font request is the slowest thing on the page.
The portal does too: it used to sit in a fallback face, with Material
Symbols showing its ligature words in the rail, until Google Fonts arrived.

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
  headline only. Three lines at desktop width so the whole tap fits a
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
- **Code** (Plex Mono 400, clamp 19-26, 1.5, +0.02em): the 32-character
  check-in code under Security, payload on one line and signature on the
  next.
- **Count** (Plex Mono 700, 28, leading 1, tabular figures): the
  lecturer's live list count; the rest of its line is muted sans.
- **Readout** (Plex Mono 400, 13, 1.55): decoded values, register rows,
  the QR's URL, the build version on /get.

Headings use `text-wrap: balance` and paragraphs `text-wrap: pretty`, so no
line ends on one stranded word. Nothing on the site renders below 12px.

### Hierarchy (portal)
- **Page Title** (Sans 700, 24px, tight tracking): one per page, in the
  page head on the grid, over a 14px secondary subtitle.
- **Card Title** (700, 14px) / **Body** (400, 14px) / **Micro** (600, 11px:
  pills, captions, help text). 11px is the smallest step.
- **Figure** (Mono 700, 24px, tabular): the facts strip's three numbers.
- **Stat Value** (Mono 700, 30px, leading 1, tabular): the stat cards that
  remain on lecturer, HOD and student pages.
- **Board Time** (Mono 700, 15px, tabular): a board row's start time and
  its checked-in count.
- **Reader** (Mono 400, 11.5px, uppercase, slight tracking, leading 1.375):
  the lines of a reader screen.
- **Column Label** (Mono 400, 11px, uppercase, widest tracking): table and
  board column heads, board group bands (bold), rail section labels,
  drawer section labels, stat labels.

### Named Rules
**The 11sp Floor Rule.** Nothing in the app renders below 11sp. The only
exception is the numeric count inside the notification badge, a single
glyph inside a pill. Sub-11 text is a bug, not a style.

**The Mono Means Machine Rule.** Monospace is only for data the system
emits (times, session and course codes, terminal states). Never use it for
labels, buttons or prose. On the site that means the check-in code, the
decoded values, times, masked student IDs, the register count, the build
version and the printed URL. Where a machine readout is followed by an
explanation, the explanation drops back to the sans. The portal has one
exception: its column labels (table and board heads, board group bands,
rail and drawer section labels, stat labels) are 11px uppercase mono, the
legend over columns of machine data. Titles, buttons, form labels and prose
stay in the sans.

**The Theme Scale Rule.** Text styles come from the theme's text scale
(`Theme.of(context).textTheme`, the portal's Tailwind scale). Never
hand-roll a font size per screen. That is how the app once had 15 sizes.

**The Own Fonts Rule.** The app, the site and the portal ship their own
Plex files. No Google Fonts, icon font or other third-party font host on
anything opened on campus Wi-Fi.

## Layout

**App.** One column, phone width, inside the safe area. Screen padding is
24dp (`EdgeInsets.all(24)`). Cards pad 16dp, sometimes 20dp. Gaps between
stacked cards and stat boxes are 12dp. Stats sit in an equal-width row
(`AppStatRow`). The student and lecturer shells use a five-tab bottom
navigation bar. Keyboard handling uses `resizeToAvoidBottomInset` with
`ClampingScrollPhysics`. Never hand-roll inset spacers.

**Portal.** A 232px Midnight rail on the left (below 1024px an
off-canvas drawer, `inert` while closed), then a column with a 56px top bar
over a scrolling page. The top bar holds Find (up to 460px, `/` to focus)
and, from 640px, the semester chip at the right. The page head and the
content share one box capped at 1680px and padded 20px (28px from 1024px),
so the title lines up with the content edge at every width. The head holds
the title and subtitle at left and the page's actions or the facts strip at
right; content stacks below it in 24px gaps. Panels pad 20px; table cells
20px x 14px, heads 20px x 10px.

Records run full width on every admin page. Occasional forms open in a
dialog and rarer actions sit in a More menu beside the title; there is no
form column beside a directory any more. Filters are one toolbar row above
the list (labels visually hidden from 1024px). Students, Lecturers and
Courses open a record in a 400px drawer on the right, under the top bar;
from 1280px the page column makes room for it, and below 1536px the list
drops its wide columns (`.col-wide`) while it is open. The door board
instead reflows each row (time and room | class and reason | action, with
the count and the reader screen beneath) while a drawer is open from 1280
to 1535px, so its actions stay in view; its reason lines wrap, never clip. A drawer holds the
jobs about that one record (a course's lecturers, enrolling a student), so
no form asks you to pick the record from a dropdown. Organization keeps its
two lists side by side (faculties and departments are peers); the
Timetable keeps its week grid, with Drafts waiting as a one-line bar above
it because publishing is the page's most consequential action.

**Site.** A 1240px column with a fluid gutter (`site-gutter`). The story
page runs as full-width bands separated by hairline rules (section padding
`site-section`, heads capped at 680px), not as a grid of equal cards. Text
and an app screenshot share a two-column split (0.8fr / 1.2fr, flipped for
alternation), and the "how it works" phone stays sticky beside its steps.
Lists of like things are **ruled rows**: a top rule, then one bottom rule
per row (the timed sequence, the threats, the roles, the /get facts).
Reading pages narrow: /get is capped at 720px, the privacy policy at 760px.

Responsive steps: above 1000px the tap is one row (phone, reader, beats);
at 1000px and below the phone and reader sit side by side (2 : 3) with the
beats under them, and the headline band stacks; at 900px splits stack; at 860px the header nav hides and an Install button takes its place;
at 760px the install band's QR hides (it is for a laptop visitor holding a
phone); at 640px primary buttons go full width and role rows stack.

## Elevation & Depth

Every surface is **flat**. Depth comes from tone and hairline borders.

The app uses `elevation: 0` everywhere. Cards are one tonal step above the
background (#0F0F0F to #1C1C1C in dark), with an outline border at
10-14% alpha. The background has a faint 28dp grid (3% alpha, 0.4 stroke)
and two large blurred-edge circles: indigo-tinted on dashboards and auth
screens, red-tinted on the change-password screen as a quiet caution
signal. These are static, sized from `MediaQuery.sizeOf`, and isolated
behind a `RepaintBoundary`.

The portal is flat as the app is: panels separate by tone (Paper page,
white panel, Raised band) and hairline, and the Midnight rail and lit reader
screens are its only dark masses. Its shadows (values in the sidecar) are
for things that float:
- **Card**: a 1px line at 3% under each panel's hairline, barely there.
- **Pop**: menus, dialogs and the skip link, anything floating above the page.
- **Drawer**: a soft shadow off the record drawer's left edge, over the page.
Dialogs dim the page behind them with Midnight at 50%.

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
- **Portal:** 12px panels, dialogs, menus and the facts strip; 8px buttons,
  inputs and the Find field; 9px rail links; 7px compact buttons and reader
  screens; 10px for the drawer's initials tile. Full pills for status pills,
  course chips, tab pills and the nav count badge. The one dashed border is
  an offline or switched-off reader screen.
- **Site:** the app's 12px for buttons, panels, the callout note and the QR
  plate; 16px for the privacy summary box; 8px for header nav links; 6px
  on the focus ring; 10px for the reader's bezel. Rows and bands have
  square edges: they are ruled, not boxed. Circles for the live dot and the /get step numerals.
  The screenshot phone frame is the one soft shape (40px outer, 31px
  screen; 26 / 20 for the smaller phone in the tap), because it is a
  drawing of a phone.

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
- **Shape:** 8px corners, 10px x 16px padding, 14px semibold. Compact variant 7px / 6px x 12px / 12px.
- **Primary:** Contactless Indigo, white text, hover to the deeper indigo step.
  The board's Notify lecturer, Add student, the drawer's Unbind phone.
- **Secondary:** Raised with a hairline border and ink text. Hover tints to
  the indigo soft step with an indigo line and indigo text.
- **Ghost:** secondary text, hover to the Paper page with ink text.
- **Danger:** error red, white text, hover #B72D32.
- **Text link** ("Edit", "Change", "Unbind"): 12px semibold muted, dotted
  underline, 24px minimum hit height. Hover turns it ink (it turned red until
  2026-10-25, which made every Edit read as a warning).
- **Disabled:** 40% opacity, no pointer events.
- **Focus:** every link, button, summary, select and tabbable element gets
  a 2px indigo outline at a 2px offset on keyboard focus.

### Status pills
- **App:** a status triple (tinted fill, edge, text) from
  `attendance_status.dart`, with uppercase labels PRESENT / LATE / ABSENT / EXCUSED.
- **Portal:** full pill, 2px x 8px, 11px semibold, selected by `data-tone`
  (never an interpolated class name). Attendance tones are a `-soft`
  background with `-ink` text. The operational tones are neutral (Paper,
  secondary text), live (indigo soft, indigo text) and ink (solid ink,
  white text); see Operational states under Colors.
- One map per side: `attendanceStatusText` / `attendanceStatusSurface` in
  the app, the `attendance_status_pill` macro on the web. Never hand-write another.

### Cards / Containers
- **App:** graphite (#1C1C1C) or white, 12dp corners, outline at 10% alpha,
  16dp padding. Record rows are 72% surfaceContainer with the same edge.
- **Portal:** white, 12px corners, hairline border, card shadow, 20px body.
  Header row, then body, then a footer separated by a divider rule. Use the
  clipped variant when a table bleeds to the edge.
- **Portal dialogs:** native `<dialog>`, white, 12px corners, 24px padding,
  up to 448px wide, centred, pop shadow over a 50% Midnight backdrop. A tall
  form scrolls inside it. Every portal modal is one (unbind, edit,
  status, delete, the confirm dialog), so focus, Tab and Escape come from
  the browser; a click on the backdrop, not the dialog's own padding,
  closes it (`SUAAMS.onBackdrop`).
- **Portal menus:** native `<details>` (opens with Enter or Space, no
  script): a 256px white list, 12px corners, pop shadow, 8px rows that hover
  to Raised.
- **Portal alerts:** 8px corners, the tone's soft tint with its ink text
  and a 25% border; info is indigo, a warning a Raised panel with a 30% ink
  edge (never amber, which is attendance's "late"), and an "act here"
  banner (a reader's new secret) indigo. Errors and warnings are
  `role="alert"`, the rest a polite status. Filter rows end in one verb,
  Apply.

### Inputs / Fields
- **App:** filled (graphite or white), no border at rest, 12dp corners, 16dp
  padding. Focus adds a 1dp border in the primary colour (white or black).
  Error adds a 1.5dp #FF5252 border. Text fields sit inside a
  `RepaintBoundary` so the blinking cursor doesn't repaint the backdrop.
- **Portal:** Raised fill, hairline border, 8px corners, indigo caret.
  Focus turns the border indigo and adds a 1px indigo ring. Destructive
  fields focus in red.
- **Find** (top bar): a 36px white field with the top bar's rule, a search
  icon at left and a `/` key hint in mono at right. Focus gives an indigo
  border and a 3px soft-indigo ring. One match or an exact matric number
  opens that student's record; more go to the roster.

### Navigation
- **App bottom nav:** surfaceContainer bar with a top hairline, five equal
  tiles. The active tile gets the accent icon and label, a 10% primary pill
  with a 28% border, and scales from 0.96 to 1.0 over 180ms ease-out-cubic.
  Labels are 11sp, never all-caps. Count badges use the primary colour;
  "something is live" uses an accent dot. Red is reserved for failure.
- **Portal rail:** Midnight, 232px. The brand block (64px) has the mark
  and the portal's name. Links are 14px medium in muted grey, 9px corners,
  and hover to Graphite with light text. The active link is Graphite with
  white text and a 2px indigo edge on its left. Section labels (Column
  Label) fold their group with a chevron that turns when closed; the choice
  is remembered per portal, and the group holding the current page always
  opens. The scroll edge is marked with a fade, not a scrollbar. A count
  that needs you (unpublished drafts) is an indigo badge with white mono
  figures. The foot holds the person's initial, name, role and Log out.
- **Portal top bar:** 56px, Top Bar indigo with its rule, Find at left and
  the semester chip at right: the term name in mono on a white plate,
  dashed and muted when no semester is active.
- **Portal page head:** the title on the 28px grid, which fades out from
  30% of the head's height toward the content. The grid is drawn on its
  own layer so only the grid fades, never the title.

### Stat boxes (signature)
A value over a caption, in an equal-width row. Neutral stats sit on a 78%
surfaceContainer with a faint edge. A success or warning stat tints its
box with the status colour at 12% fill and 35% border. Tone is set
explicitly (`AppStatTone`) and is never derived from the label text. The
portal's equivalent, the stat card, remains on lecturer, HOD and student
pages: a mono column label, a 30px mono value, and an 11px caption. The
admin home replaced its row of stat cards with the facts strip.

### Door board (portal signature)
The admin home: every room's class today, and what its reader is showing,
on one board.
- **Facts strip:** three figures in a white hairline strip beside the title
  (need you, classes live, readers online), Figure over a muted line.
  "Need you" turns indigo when it isn't zero.
- **Board:** one white panel. A Raised column header in Column Label, then
  groups as Raised bands with the group's name and count: Needs you, Live
  now, Due now, Later today, Ended. The Needs you band and its rows take the
  indigo soft tint and line.
- **Rows:** five columns that never move. Time (Board Time) over the room;
  course code in mono and title, then lecturer and the reason in secondary
  ("no session 42 min after start", "reader last seen 27 min ago"); checked
  in ("188 of 204") over a 4px ink bar on Divider, or "Not started" /
  "in 78 min"; the reader screen; the action at the right (Notify lecturer
  primary; Remind again or Open reader secondary; otherwise a mono note,
  "ends 11:00"). Below 1024px a row stacks.
- **Refresh:** every 15 seconds the server re-renders the facts and rows
  and they are swapped in place, skipped while keyboard focus is inside the
  board. A failed refresh turns the clock in the subtitle into "as of 10:42"
  followed by "reconnecting", in indigo mono.
- **Under the board:** one line of today's check-ins by method (a dot, the
  method, a mono percentage; NFC's dot indigo, the rest neutral), then a
  ruled Latest check-ins log beside the department attendance bars.

### Reader screen (portal)
What the room's reader shows, in the firmware's own words
(`oled_display.ino`): Reader type, uppercase, 7px corners, at least 40px
tall. Never an attendance colour: these are machine states.
- **Lit** (a class is running): Midnight with light text, as the reader's
  own screen, with a dark-value indigo live dot ringed at 25% before the
  first line: "MCT 401", "188 / 204 CHECKED IN", "ENDS 11:00".
- **Dim** (idle): Raised with a hairline and muted text ("NO CLASS", the
  next class).
- **Off** (offline or switched off): white with a dashed ink border:
  "READER OFFLINE", "TAPS HELD ON READER".
- **None** (no reader, or no room on the timetable): a plain muted
  sentence-case line, no box. A later class whose reader is lit for another
  class says so in a line instead of repeating that screen.

### Record drawer (portal)
A student's record and everything you can do to them, opened from Find or
a name on the board or the roster, while the page behind stays in view.
- **Frame:** fixed on the right under the top bar, 400px (full width on a
  phone), white with a hairline left border and the drawer shadow. Its URL
  can be shared; the close link and Escape go back.
- **Head:** a 44px Midnight initials tile, the name (18px bold), matric
  number, level and department in mono secondary, a 32px close button.
- **Sections**, ruled by Divider, each under a Column Label: Account (a key
  and value list, muted keys), Phone (binding and its date), Attendance this
  semester (standing), Recent changes (a dated log with who made each).
- **Actions** pinned on a Raised bar at the bottom, so they sit in the same
  place whatever the record holds: Unbind phone... (primary, full width, only
  while a phone is bound), Change status, Reset password, Edit record.
- The roster row of the open record takes the indigo soft tint.

### Exam standing (portal)
One line per course: the code in mono, a 6px bar on Divider, the
percentage in mono. The bar fills green at or above the exam line and amber
below it, and every bar carries a 1px ink tick (45% opacity) at the line,
75% today. Below it the percentage turns bold amber ink and a line says so
in words ("Below 75%: not yet eligible for the exam"). A key under the
list explains the tick.

### One-time password (portal)
A new temporary password is shown once, as an indigo soft panel with an
indigo line: who it is for and a muted note, then the password on a Midnight
plate in 18px mono with wide tracking (select-all on click) and a Copy
button, which says "Copied" or selects the text where the clipboard isn't
allowed.

### Confirm dialog (portal)
Every "are you sure" is the portal's own dialog (`SUAAMS.ask`,
`_head_assets.html`), never the browser's `confirm()`: a title that names
the thing ("Make 2026/2027 First Semester the active semester?"), one plain
sentence on what changes, Cancel, and a button that names the action
("Make active", "Publish", "Disable reader"). The action is indigo, or red
only when it destroys something, and then Cancel takes the first focus so
Enter can't destroy. An action that can't be undone and stops hardware
(a reader's new secret) asks for the record's own code to be typed before
its button enables. Forms opt in with `data-confirm` (plus
`-title`, `-ok`, `-danger`) or `SUAAMS.confirmSubmit`.

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

### The tap (site signature)
The story page's first screen, under the headline band: the two screens a
student actually looks at during a check-in, **their phone** and **the
reader at the door**, stepping together through three numbered beats
written in plain words beneath them. It replaced (2026-10-25) a three-column
IN | reader | OUT stage whose decoded code and register most visitors
couldn't read, on a phone least of all; the code now sits under Security
("What your phone actually sends") and the live list under Lecturers.
- **Phone:** the app's real screens (demo account) in the phone frame at
  its smaller size (6px bezel, 26px outer corner), one per beat, stacked
  and crossfading (250ms): the ID card with its Check in button, the
  "Listening for terminal" sheet, "Attendance verified" with its
  notification. The fingerprint prompt can't be screenshotted, so beat 1
  is the button that opens it.
- **Reader:** a faint "The reader at the door" label over a drawing of the
  reader's own 0.96" 128x64 OLED, made from the firmware
  (`oled_display.ino`): an SVG on the OLED's pixel grid (viewBox 0 0 128
  64, text in Plex Mono at the GFX 6 px advance, faces from
  `oledDrawFace()`), black glass and white pixels in both themes, in a
  #050505 bezel. Its screens change with no fade, like a frame redraw:
  the class screen at 186 with "TAP your phone"; WAIT / "Checking..."
  with the bar creeping (it fills over 10 s on the device); DONE, "Shang",
  "marked present". Never invent hardware beyond it: no enclosure or
  antenna is drawn.
- **Beats:** three ruled rows, a number in indigo Readout, a title and one
  muted line: *Confirm it's you*, *Tap the reader*, *You're marked*. Done
  and current beats are lit, later ones faint, so the list reads as
  progress; finished, all three are lit. Numbers here are earned: the
  order is the content.
- **Layout:** above 1000px one row: phone (220px), reader, beats (260-340px).
  At 1000px and below, phone and reader side by side (2 : 3, phone capped at
  240px) with the beats full width under them; at 390px the whole tap is
  about 570px tall, so it fits one phone screen.
- **Demo label:** a faint caption under the tap ("Demo account and reader
  screen, not real students."); "Replay the tap" sits opposite it.
- **Motion (hero.js), played once:** when the beats list is 90% in view
  (bottom 8% of the window excluded), beat 1 holds 1.6s (the person acts:
  slow), beat 2 holds 1.3s (the system answers: quicker), then beat 3 is the
  end state. As beat 2 starts the reader's bezel flashes a 2px indigo ring
  once, its "beep" (300ms). The script only sets `data-beat` on `.tap`;
  styles.css draws each beat from it.
  - The markup is the finished state (`data-beat="3"`). An inline script in
    `<head>` adds `.motion` before first paint, and CSS shows beat 1 until
    hero.js takes over (`.armed`), so there's no flash of the finished
    tap; a 3s fallback (`.motion-done`) shows the finished tap if hero.js
    never arrives. With no script the finished tap is plain markup.
    Reduced motion: the screens still change, as fades, and the bar
    doesn't travel.

### The hall (site)
The one quiet statement after the tap, and the page's second visual beat:
the tap shows one student, the hall shows a whole lecture.
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
  are hidden under `.motion` (the same 3s fallback as the tap). Reduced
  motion, no IntersectionObserver or no script: the grid simply shows.
  `overflow-x: clip` on the section keeps spilled dots from widening the
  page.

### Ruled rows (site)
- **Timed sequence** ("how it works"): a 112px marker column with the time
  in indigo Readout (`t = 0`, `within 10 s`, `+ ~0.5 s`), then a title and
  muted body. The times are the markers; there are no step numbers. The
  section heading sits beside it on desktop. No screenshots: the tap
  already shows each step's screen, so this is the same check-in in
  detail, with its timings.
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
dot and arcs. Drawn by `SuaamsLogo` (CustomPainter) in the app, by one
inline SVG symbol on the site, and by the portal's `suaams_mark` macro (same
geometry), with the body strokes in `currentColor` (white on the rail, ink
on a light card). Never recolour the dot or arcs to the indigo accent.

## Do's and Don'ts

### Do:
- **Do** use Contactless Indigo only on the active tab, the check-in action, contactless glyphs and live dots.
- **Do** keep portal indigo to act here, you are here, needs you and live: the primary button, the active rail edge and tab, focus, the Needs you band and figure, live pills.
- **Do** show portal machine and lifecycle states as neutral, indigo or the solid ink pill, and reader screens in the firmware's own words.
- **Do** pair every status colour with its text label, from the one shared map on each side.
- **Do** read colours from `AppTerminal` / `colorScheme` (app) or the `@theme` tokens (portal). Never retype a hex at a call site.
- **Do** keep app tap targets at 48dp or more, and full-width primary buttons at 56dp tall.
- **Do** set times, codes and terminal strings in the mono face, and everything else in the sans.
- **Do** contrast-check new pairs against the surface they actually sit on, including tinted fills.
- **Do** build site pages from the app's tokens and the `styles.css` custom properties; dark by default, light by `prefers-color-scheme`.
- **Do** label every piece of sample data as demo, next to it: the tap, the demo code, the lecturer's live list, and every screenshot caption.
- **Do** separate site lists with ruled rows (hairline top and bottom), not cards.
- **Do** make every site animation finish into the page's static markup, so no script or reduced motion shows the complete state.
- **Do** self-host fonts on every surface (Plex WOFF2, `font-display: swap`), and inline portal icons as SVG from `icons.py`.
- **Do** run portal records full width, with occasional forms in a dialog and the record in the drawer.

### Don't:
- **Don't** use green for anything except "present / success".
- **Don't** render app text below 11sp, or hand-roll a `TextStyle` font size outside the theme scale.
- **Don't** use the raw status hues (#10B981, #F59E0B, #EF4444) as text. They are fills only.
- **Don't** add drop shadows to app surfaces. Step the tone instead.
- **Don't** build portal tone classes by string interpolation (`bg-{{ tone }}`). Use `data-tone`.
- **Don't** load Google Fonts, an icon font or any third-party font on the app, the site or the portal.
- **Don't** add a second accent to the site or the portal, or use Brand Blue anywhere but the logo mark.
- **Don't** colour a live class, a check-in method, a draft count or a lifecycle state green or amber in the portal; those are attendance's colours.
- **Don't** set prose, headings, labels or buttons in Plex Mono on the site; explanations under a readout go back to the sans.
- **Don't** add box shadows to the site. Step from Midnight to Sunk to Graphite instead.
- **Don't** carry the poster's light sheet onto screen pages; it is the print exception.
