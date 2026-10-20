"""Regression guards for the web templates and the light-theme design system.

Added with the 2026-09-30 redesign. Each test pins one property that is easy
to break silently and expensive to notice by eye:

  1. Every template still parses. A Jinja syntax error in one page takes out
     that page only, so it tends to be discovered by a user rather than a
     test run.
  2. The shell's DOM contract is intact. The rail script and its CSS both
     reach for #sidebar, #sidebar-backdrop and #sidebar-toggle; renaming or
     dropping one leaves the navigation dead on every page with no error.
  3. No template builds a Tailwind class by string interpolation. This is the
     big one -- Tailwind scans source TEXT for complete class-name tokens, so
     a class assembled across a Jinja expression is invisible to it. The rule
     is simply never emitted and the element renders unstyled, silently.
     The templates use data-tone attributes for exactly this reason.
  4. The theme stayed light. Guards the token block against being reverted to
     the old dark values by a copy-paste from git history.
  5. Form inputs are not white-on-white. The old .form-input hardcoded
     `text-white`, which governed ~40 inputs app-wide and was invisible until
     the background changed underneath it.

Run with:  python tests/test_templates.py
(also collected by pytest if it is installed)
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
INPUT_CSS = ROOT / "static" / "src" / "input.css"


def _templates():
    return sorted(TEMPLATES.rglob("*.html"))


def test_every_template_parses():
    """A syntax error in one template breaks that page only, so it survives
    long enough to be found by a user. Cheap to check, so check it."""
    import jinja2

    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(TEMPLATES)))
    failures = []
    for path in _templates():
        name = path.relative_to(TEMPLATES).as_posix()
        try:
            env.parse(path.read_text(encoding="utf-8"), filename=name)
        except Exception as exc:  # noqa: BLE001 - report every one, not just the first
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    assert not failures, "Template syntax errors:\n  " + "\n  ".join(failures)


def test_shell_dom_contract():
    """#sidebar / #sidebar-backdrop / #sidebar-toggle are the rail script's
    only inputs (the desktop #rail-collapse toggle was removed). Since the
    2026-09-30 consolidation these all live in the shared _shell, so the
    portal templates are checked for extending it rather than for carrying
    the ids themselves."""
    for shell in ("base_admin.html", "base_portal.html", "base_student.html"):
        source = (TEMPLATES / shell).read_text(encoding="utf-8")
        assert '{% extends "_shell.html" %}' in source, (
            f"{shell} should extend _shell.html -- the rail, topbar and flash "
            "loop live there"
        )

    shared = (TEMPLATES / "_shell.html").read_text(encoding="utf-8")
    for hook in ("shell", "sidebar", "sidebar-backdrop", "sidebar-toggle"):
        assert f'id="{hook}"' in shared, f"_shell.html is missing id=\"{hook}\""


def test_no_split_tailwind_class_names():
    """The redesign's biggest silent-failure mode.

    A class name is assembled at RENDER time, long after Tailwind has already
    scanned the source, so the scanner only sees whatever literal fragments
    happen to be in the file. If the class is SPLIT across a Jinja expression
    -- class="bg-{{ tone }}" -- the scanner sees the fragments `bg-` and
    `tone`, never `bg-success`, the rule is dropped from the compiled CSS, and
    the element renders unstyled with no exception, no warning and no
    missing-icon marker. Just a quietly wrong-looking page.

    Note what this test deliberately does NOT flag. The ternary form
    class="nav-link {{ 'nav-link-active' if cond }}" is SAFE and is the
    established convention here: both branches are complete literal class
    names sitting in the source text, so the scanner finds each one. It only
    breaks if the class is split with no space before the expression, which is
    what the pattern below matches.

    Colour still travels in a data-tone attribute (see _macros.html), because
    that is robust regardless of what the surrounding markup happens to say.
    """
    # A class-name character immediately followed by {{ -- i.e. a split name.
    pattern = re.compile(r'class="[^"]*[\w-]\{\{')
    violations = []
    for path in _templates():
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if pattern.search(line):
                rel = path.relative_to(TEMPLATES).as_posix()
                violations.append(f"{rel}:{lineno}: {line.strip()[:110]}")
    assert not violations, (
        "Split Tailwind class names (these vanish from the compiled CSS with "
        "no error):\n  " + "\n  ".join(violations)
    )


def test_theme_is_light():
    """Guards against a copy-pasted revert to the pre-redesign dark values."""
    css = INPUT_CSS.read_text(encoding="utf-8")
    for dark_hex in ("#0F1117", "#1C1E26", "#111318", "#2A2D3A"):
        assert dark_hex.lower() not in css.lower(), (
            f"{dark_hex} is one of the old dark-theme surfaces; the redesign "
            "is a light theme"
        )
    # The rail stays dark on purpose -- that contrast is the whole design.
    assert "#14161F" in css, "the dark navy rail token is missing"


def test_form_inputs_are_not_white_on_white():
    """Regression guard for the single highest-impact dark-theme leftover:
    .form-input hardcoded `text-white`, which governed every input in the app
    and became invisible the moment the field background went light."""
    css = INPUT_CSS.read_text(encoding="utf-8")
    form_block = re.search(
        r"\.form-input[^{]*\{(.*?)\}", css, re.DOTALL
    )
    assert form_block, "could not find the .form-input rule in input.css"
    assert "text-white" not in form_block.group(1), (
        ".form-input must not hardcode text-white -- primary text on a light "
        "surface is --color-ink"
    )


def test_material_symbol_hidden_guard_is_unlayered():
    """Guards a bug that showed two eye icons at once on the login page.

    Google Fonts' Material Symbols stylesheet is UNLAYERED and declares
        .material-symbols-rounded { display: inline-block }
    Tailwind v4 puts everything in cascade layers, and unlayered author styles
    beat every layered rule regardless of specificity. So Tailwind's `.hidden`
    silently does nothing on an icon span, and the password eye toggles --
    which are two spans, one carrying `hidden` -- rendered both.

    The fix only works if it is UNLAYERED too: inside `@layer utilities` it
    still loses to Google no matter how many classes the selector has. This
    asserts the guard is present AND not inside a layer block, because moving
    it back into a layer looks harmless and reintroduces the bug.
    """
    css = INPUT_CSS.read_text(encoding="utf-8")

    assert ".material-symbols-rounded.hidden" in css, (
        "the Material Symbols / .hidden cascade guard is missing from input.css"
    )

    # Find the rule and make sure no enclosing @layer wraps it.
    idx = css.index(".material-symbols-rounded.hidden")
    before = css[:idx]
    opens = before.count("@layer")
    closes = before.count("}")
    assert opens <= closes, (
        "the .material-symbols-rounded.hidden guard is inside an @layer block; "
        "it must stay unlayered or it will lose to the Google Fonts icon "
        "stylesheet again (this is what caused the doubled eye icon)"
    )


def test_password_eye_toggle_semantics():
    """The two eye icons were also wired backwards: while the field was masked
    the page showed the crossed-out eye, so clicking what looked like "hide"
    revealed the password. Assert the plain eye is the one shown when masked."""
    for page in ("login.html", "change_password.html"):
        src = (TEMPLATES / "auth" / page).read_text(encoding="utf-8")
        assert "eyeIcon.classList.toggle('hidden', revealed)" in src, (
            f"auth/{page}: the plain eye should be hidden only once revealed"
        )
        assert "eyeOffIcon.classList.toggle('hidden', !revealed)" in src, (
            f"auth/{page}: the crossed-out eye should be hidden while masked"
        )


# Every Material Symbols ligature this app is allowed to use. Verified by
# rendering each one in a real browser and looking at it: a name that is NOT
# in the font does not error and does not draw a box -- it renders as literal
# text ("graduation_cap" appears on screen as the word GRADUATION_CAP), which
# is completely silent.
#
# The trap is that Material Icons (the other font family) has names Material
# Symbols does not -- graduation_cap, for one, is a Material Icons name. Both
# families are served from the same Google endpoint, so it is easy to reach for
# the wrong one. Adding a name here means you have looked at it rendered.
VERIFIED_MATERIAL_SYMBOLS = {
    "account_tree", "analytics", "book", "calendar_month", "campaign",
    "check", "chevron_right", "close", "co_present", "dashboard",
    "date_range", "delete", "download", "event_available", "expand_more",
    "groups_2", "history", "info", "layers", "left_panel_close", "lock",
    "login", "logout", "menu", "person", "play_circle", "schedule",
    "school", "sensors", "stop_circle", "summarize", "task_alt",
    "visibility", "visibility_off", "warning",
    # `inbox` is the empty_state() macro's default only -- no page passes it.
    "inbox",
    # "Accept all" on the lecturer's offline-tap review. Checked 2026-10-12
    # against Google's MaterialSymbolsRounded codepoints file (e877), which
    # also confirms graduation_cap above is absent from this family.
    "done_all",
    # Assigned from JS rather than markup: the rail collapse control swaps its
    # glyph via textContent so it keeps pointing the way the rail is about to
    # move. Included here because the markup scan below cannot see it.
    "left_panel_open",
    # Passed positionally to empty_state() / stat_card(), which the scan
    # below did not read until 2026-10-16, plus the Terminals page's key and
    # nfc. All rendered side by side in headless Chrome against the same
    # Google Fonts stylesheet the app loads, and looked at, on 2026-10-16.
    "key", "nfc", "domain", "domain_disabled", "event", "event_busy",
    "event_note", "group", "groups", "how_to_reg", "insights", "query_stats",
    "search_off", "verified", "event_available", "trending_up", "trending_down",
    # Admin rail, 2026-10-19: HODs (was workspace_premium, a medal -- read as
    # an award) and Activity (was history, the same glyph as the two history
    # pages, for what is an audit log). Rendered and looked at that day.
    "supervisor_account", "manage_history",
}

# The icon passed positionally to the macros that take one: the second
# argument of empty_state(message, icon) and the fourth of
# stat_card(label, value, caption, icon, ...). Only quoted literals count.
_POSITIONAL_ICON = re.compile(
    r"empty_state\([^,()]+(?:\([^()]*\))?[^,()]*,\s*'([a-z_0-9]+)'\s*\)"
    r"|stat_card\((?:[^,()]+(?:\([^()]*\))?[^,()]*,\s*){3}'([a-z_0-9]+)'")

# Names a script writes into a Material Symbols element. The markup regex
# cannot see these, and a glyph that does not exist renders as its own name in
# body text -- exactly as invisible here as it is in a template.
_JS_ICON_ASSIGNMENT = re.compile(r"textContent\s*=\s*'([a-z_0-9]+)'")


def test_rail_keyboard_and_screen_reader_contract():
    """The side rail (2026-10-18): every portal marks its active link with
    aria-current, hides its decorative icons from screen readers, and the
    shell has a "Skip to content" link to #main and the rail's "more below"
    fades -- the admin rail runs past a laptop screen, and its scrollbar is
    hidden, so the fade is what says there's more."""
    for name in ("base_admin.html", "base_portal.html", "base_student.html"):
        source = (TEMPLATES / name).read_text(encoding="utf-8")
        for m in re.finditer(r"\{\{ 'nav-link-active' if (.+?) \}\}\"", source):
            tail = source[m.end():m.end() + 200]
            assert 'aria-current="page"' in tail, f"{name}: active link without aria-current ({m.group(1)})"
        icons = re.findall(r'<span class="material-symbols-rounded[^"]*"[^>]*>', source)
        unhidden = [i for i in icons if 'aria-hidden="true"' not in i]
        assert not unhidden, f"{name}: rail icons read aloud: {unhidden[:3]}"
    shell = (TEMPLATES / "_shell.html").read_text(encoding="utf-8")
    assert '<a href="#main" class="skip-link">' in shell
    assert 'id="main"' in shell
    assert 'id="rail-fade-bottom"' in shell and 'id="rail-fade-top"' in shell
    assert 'aria-controls="sidebar"' in shell


def test_collapsible_rail_sections_point_at_their_groups():
    """Every collapsible heading (rail_section, 2026-10-19) controls a group
    that exists: aria-controls="rail-sec-<key>" must match an id in the
    same template, or the button folds nothing. Admin and lecturer rails
    only; the student and HOD rails are short and stay plain."""
    for name, expected in (("base_admin.html", 6), ("base_portal.html", 5)):
        source = (TEMPLATES / name).read_text(encoding="utf-8")
        keys = re.findall(r'rail_section\("[^"]+", "([a-z0-9-]+)"\)', source)
        assert len(keys) == expected, f"{name}: {len(keys)} collapsible sections, expected {expected}"
        for key in keys:
            assert f'id="rail-sec-{key}"' in source, f"{name}: no group for section {key}"
    assert "rail_section(" not in (TEMPLATES / "base_student.html").read_text(encoding="utf-8")


def test_hod_roster_header_and_rows_share_one_grid():
    """The HOD Students roster (2026-10-19): the header and every row's
    summary use the same column template, so they can't drift apart again
    (it was a <table> header over full-width flex rows -- matric numbers sat
    under "Overall Attendance")."""
    source = (TEMPLATES / "hod" / "students.html").read_text(encoding="utf-8")
    templates = re.findall(r'class="(grid grid-cols-\[[^"]*?) (?:border-b|cursor-pointer)', source)
    assert len(templates) == 2, templates
    assert templates[0] == templates[1], templates
    assert "_auto]" not in templates[0], "an auto last column sizes differently in header and rows"


def test_admin_dropdowns_dont_submit_on_change():
    """No admin page reloads when a dropdown changes (2026-10-18). On
    Windows an arrow key on a closed <select> fires change, so a page that
    submitted on change reloaded on the first press -- you couldn't reach
    the option you wanted, focus jumped to the top (WCAG 3.2.2), and on
    Analytics each reload re-ran the whole eligibility calculation. Filters
    apply with their button instead. The other portals aren't reviewed yet,
    so this covers templates/admin only."""
    offenders = [
        str(path.relative_to(TEMPLATES))
        for path in sorted((TEMPLATES / "admin").glob("*.html"))
        if "form.submit()" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"submit-on-change is back in: {offenders}"


def test_icon_names_exist_in_the_font():
    """Guards against the silent 'renders as text' failure described above."""
    pattern = re.compile(r"material-symbols-rounded[^>]*>([^<>{}]{2,30})<")
    arg_pattern = re.compile(r"\bicon='([a-z_0-9]+)'")

    used = set()
    for path in _templates():
        source = path.read_text(encoding="utf-8")
        used.update(m.group(1).strip() for m in pattern.finditer(source))
        # only icon= arguments that name a glyph, not prose
        used.update(m.group(1) for m in arg_pattern.finditer(source))
        used.update(m.group(1) for m in _JS_ICON_ASSIGNMENT.finditer(source))
        used.update(m.group(1) or m.group(2) for m in _POSITIONAL_ICON.finditer(source))

    unknown = sorted(used - VERIFIED_MATERIAL_SYMBOLS)
    assert not unknown, (
        "icon name(s) not in the verified Material Symbols set. A name that is "
        "not in the font renders as literal text with no error, so confirm the "
        f"glyph visually before adding it: {unknown}"
    )


def test_data_tone_contract_is_complete():
    """Every tone the templates pass must have a matching rule in input.css,
    or the element falls back to an unstyled pill."""
    css = INPUT_CSS.read_text(encoding="utf-8")
    for tone in ("success", "warning", "error", "accent", "neutral"):
        assert f'[data-tone="{tone}"]' in css, (
            f"no CSS rule handles data-tone=\"{tone}\""
        )


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS  {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {test.__name__}\n      {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {test.__name__}: {type(exc).__name__}: {exc}")
    print()
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
