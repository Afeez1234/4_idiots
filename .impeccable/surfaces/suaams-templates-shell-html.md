---
version: 1
slug: "suaams-templates-shell-html"
primary_target: "SUAAMS/templates/_shell.html"
related_targets: ["SUAAMS/templates/base_admin.html","SUAAMS/templates/base_portal.html","SUAAMS/templates/base_student.html","SUAAMS/templates/admin/dashboard.html","SUAAMS/templates/admin/students.html"]
---

# Surface brief: web portal (portal.suaams.com.ng)

Mode: Operate. Flask/Jinja + Tailwind v4 (`static/src/input.css` -> `output.css`). One shell (`_shell.html`) for admin, lecturer/HOD and student web; ships on admin pages first.

## Audience and job
- Admins at a registry desk, often with a student standing there; bulk record work. Two jobs: is today's teaching happening, and find this person and fix their problem.
- Lecturers, HODs, students: same shell, their own nav.

## Proof and content
- Board data that exists: today's timetable slots (`dashboard_today.py` states, `LATE_AFTER`), sessions and live check-in counts, `Terminal.room` / `last_seen_at` / `is_active`.
- Drawer data that exists: student record, status, binding (+ `device_bound_at`, new), per-course attendance against `EXAM_ELIGIBILITY_THRESHOLD`, audit log entries for that student. Never phone model or last sign-in (not stored).

## Direction contract
THESIS: The desk sees every door at once, and any person is one keystroke away without leaving it. Refuses the generic admin kit: navy rail, stat-card row, form column beside a directory, a dashboard of equal cards.
OWN-WORLD: the app's Midnight Instrument in light at desk width: Midnight #0F0F0F rail, indigo-tinted Paper ground #E9EBF6 with a soft indigo top bar #DCE0F6, white panels, cool hairlines #D6D9EA, IBM Plex Sans + Plex Mono (machine data only), Contactless Indigo #4F46E5 as the one act-here signal, faint 28px grid behind page heads. Attendance tones for attendance only; operational states in ink, indigo or dashed outline.
STORY: An admin opens the portal, reads in under 10 seconds which rooms need them, acts in one click, and reaches any student's record in under three actions while the board stays in view.
FIRST VIEWPORT: Rail left; tinted top bar with a white Find field (`/`) and the semester chip; page head on the grid with title and a three-figure strip (need you, classes live, readers online); the door board full width: column header, then groups Needs you (indigo band, one button per row), Live now, Later today, Ended; five columns: time + room, class + lecturer, checked in, reader shows, action. A student's record drawer opens on the right: header, account, phone, attendance with the 75% tick, recent changes, pinned actions (Unbind phone..., Reset password, Edit record).
FORM: the dealt lead (door board) fused with dealt structure two (register + record drawer) on the user's steer; seed:8c595ce2751ee2e1. Signature move: each board row echoes what its reader is showing, lit Midnight readout while a class is live, dim when idle, dashed when offline; rows are live entities ranked by time, columns never move, values update in place (poll 15 s).
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Open decisions
- Lecturer analytics colours below-75% red; student home and portal use amber. Align the app later.
