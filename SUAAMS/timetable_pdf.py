"""Read a Student Affairs lecture timetable PDF into class slots.

What the PDFs look like (see tests/fixtures/timetables/)
--------------------------------------------------------
One sheet per department per level, e.g. "200 LEVEL B.SC. - ACCOUNTING".
A grid: days down the side (MON..SAT), one-hour columns across the top
("0800:0900" .. "1700:1800"). Each filled cell holds two lines:

    ACC204(L)        <- course code + kind: (L)ecture, (T)utorial, (P)ractical
    HALL C3          <- room

Back-to-back cells for the same class are one longer class: ACC212(L) LR 102
at 08:00 and at 09:00 is a single Monday 08:00-10:00 slot.

Why it is read letter by letter
-------------------------------
The program that makes these PDFs places every letter separately, and a
cell's two lines come out interleaved ("A F I T L - A R ..."), with bold text
drawn twice. So each letter is put into its grid cell by its position, the
cell is split into its top and bottom line, and the letters are re-joined
left to right.

Why the page is rendered
------------------------
The PDF text layer contains entries that are NOT printed -- in the sample, a
"BUS208(L) EED HALL" on Wednesday and a "FOS LR2" on Friday sit in the file
but the page shows those cells empty. Trusting the text layer would invent
classes. So the page is rendered like a viewer would, and a letter only
counts if there is ink where it sits. Measured on the sample: hidden letters
leave 0 dark pixels, printed ones at least 8; the cut-off is 3.

Only the single-page landscape layout is accepted. The same timetable can
also come out split over several portrait pages (no header, day names on the
first page only); that is refused with a clear message instead of guessed at.

Nothing here touches the database: it returns what it read, and the admin
preview decides what to save.
"""
import re
from dataclasses import dataclass, field
from datetime import time

import pdfplumber
import pypdfium2 as pdfium

DAYS = {'MON': 0, 'TUE': 1, 'WED': 2, 'THU': 3, 'FRI': 4, 'SAT': 5, 'SUN': 6}
KINDS = {'L': 'Lecture', 'T': 'Tutorial', 'P': 'Practical'}

_TIME_HEADER = re.compile(r'^(\d{2})(\d{2}):(\d{2})(\d{2})$')
# AFIT-ACC212(L), ACC204(T), GST 212(L), MTH101A(P)
_CODE_LINE = re.compile(r'^([A-Z]{2,6}(?:-[A-Z]{2,6})?\s?\d{3}[A-Z]?)\s*\(([LTP])\)$')
_LEVEL = re.compile(r'\b(\d)00\s*LEVEL\b')
_DEPARTMENT = re.compile(r'\bDEPARTMENT OF\s+(.+)$')
_SEMESTER = re.compile(r'\b(FIRST|SECOND|THIRD)\s+SEMESTER\s+(\d{4}/\d{4})')

RENDER_SCALE = 4        # pixels per PDF point when checking ink
INK_DARK = 160          # grey level below which a pixel counts as ink (0-255)
INK_MIN_PIXELS = 3      # a letter with less ink than this is not printed


class TimetablePdfError(Exception):
    """The file can't be read as a timetable sheet. The message is shown to
    the admin as-is, so it says what to do about it."""


@dataclass
class ParsedSlot:
    code: str           # 'AFIT-ACC212', 'ACC204' -- as printed
    kind: str           # 'L', 'T' or 'P'
    day: int            # 0 = Monday ... 6 = Sunday
    start: time
    end: time
    room: str

    @property
    def kind_name(self):
        return KINDS[self.kind]


@dataclass
class ParsedSheet:
    department: str | None      # 'Accounting'
    level: int | None           # 200
    semester: str | None        # 'Second Semester 2025/2026'
    slots: list[ParsedSlot] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def normalize_code(code):
    """'ACC 206' and 'acc206' are the same course: compare without spaces."""
    return re.sub(r'\s+', '', code or '').upper()


def parse_timetable_pdf(source):
    """Read one timetable sheet. `source` is a path or a binary file object.
    Raises TimetablePdfError if it isn't a single-page sheet in the known
    layout."""
    try:
        pdf = pdfplumber.open(source)
    except Exception as e:  # corrupt file, not a PDF, encrypted
        raise TimetablePdfError("This file couldn't be opened as a PDF.") from e

    with pdf:
        if len(pdf.pages) != 1:
            raise TimetablePdfError(
                f"This PDF has {len(pdf.pages)} pages. The timetable must be on ONE "
                "landscape page -- print or export it as a single landscape page "
                "and upload that.")
        page = pdf.pages[0]
        columns, header_bottom = _find_columns(page)
        rows = _find_rows(page, columns, header_bottom)
        sheet = _read_header(page, header_bottom)
        ink = _ink_checker(source, page)
        cells = _letters_by_cell(page, columns, rows, ink)

    for (day, col), letters in sorted(cells.items()):
        lines = _lines(letters)
        if not lines:
            continue
        where = f"{_day_name(day)} {columns[col][0].strftime('%H:%M')}"
        match = _CODE_LINE.match(lines[0])
        if not match:
            sheet.warnings.append(f"{where}: couldn't read \"{' / '.join(lines)}\" -- skipped.")
            continue
        room = ' '.join(lines[1:]).strip()
        start, end = columns[col][0], columns[col][1]
        sheet.slots.append(ParsedSlot(normalize_code(match.group(1)), match.group(2),
                                      day, start, end, room))

    sheet.slots = _merge_back_to_back(sheet.slots)
    if not sheet.slots:
        sheet.warnings.append('No classes were found on this sheet.')
    return sheet


# ---- layout -------------------------------------------------------------------

def _find_columns(page):
    """([(start, end, left_x, right_x), ...], header_bottom_y) from the
    '0800:0900' headers."""
    headers = []
    for w in page.extract_words():
        m = _TIME_HEADER.match(w['text'])
        if m:
            h1, m1, h2, m2 = map(int, m.groups())
            headers.append((time(h1, m1), time(h2, m2), (w['x0'] + w['x1']) / 2, w['bottom']))
    if len(headers) < 2:
        raise TimetablePdfError(
            "No hour columns (like 0800:0900) were found. This doesn't look like "
            "a Student Affairs lecture timetable sheet.")
    headers.sort(key=lambda h: h[2])
    centers = [h[2] for h in headers]
    gaps = [b - a for a, b in zip(centers, centers[1:])]
    half = min(gaps) / 2
    bounds = [centers[0] - half] + [(a + b) / 2 for a, b in zip(centers, centers[1:])] + [centers[-1] + half]
    cols = [(h[0], h[1], bounds[i], bounds[i + 1]) for i, h in enumerate(headers)]
    # Where the header row ends; the day rows start below it.
    return cols, max(h[3] for h in headers)


def _find_rows(page, columns, header_bottom):
    """{day: (top_y, bottom_y)} from the day labels left of the grid."""
    left_edge = columns[0][2]
    labels = sorted(
        ((DAYS[w['text']], (w['top'] + w['bottom']) / 2)
         for w in page.extract_words()
         if w['text'] in DAYS and w['x1'] <= left_edge),
        key=lambda d: d[1])
    if not labels:
        raise TimetablePdfError("No day names (MON, TUE, ...) were found down the side of the grid.")
    centers = [c for _, c in labels]
    gap = min((b - a for a, b in zip(centers, centers[1:])), default=24)
    bounds = ([header_bottom]
              + [(a + b) / 2 for a, b in zip(centers, centers[1:])]
              + [centers[-1] + gap / 2])
    return {day: (bounds[i], bounds[i + 1]) for i, (day, _) in enumerate(labels)}


def _read_header(page, header_bottom):
    """Department, level and semester from the title lines above the grid."""
    top = page.crop((0, 0, page.width, header_bottom - 12))
    text = (top.extract_text() or '').upper()
    sheet = ParsedSheet(department=None, level=None, semester=None)
    for line in text.splitlines():
        line = line.strip()
        if m := _DEPARTMENT.search(line):
            sheet.department = m.group(1).strip().title()
        if m := _LEVEL.search(line):
            sheet.level = int(m.group(1)) * 100
        if m := _SEMESTER.search(line):
            sheet.semester = f"{m.group(1).title()} Semester {m.group(2)}"
    if sheet.department is None or sheet.level is None:
        sheet.warnings.append(
            "Couldn't read the department and level from the sheet's title -- "
            "check them in the preview.")
    return sheet


# ---- letters ----------------------------------------------------------------

def _ink_checker(source, page):
    """A function telling whether a letter actually shows on the rendered page."""
    if hasattr(source, 'seek'):
        source.seek(0)
        doc = pdfium.PdfDocument(source.read())
    else:
        doc = pdfium.PdfDocument(source)
    image = doc[0].render(scale=RENDER_SCALE).to_pil().convert('L')
    pixels = image.load()
    width, height = image.size

    def visible(c):
        # The middle of the letter's box only: its edges can touch grid lines.
        w, h = c['x1'] - c['x0'], c['bottom'] - c['top']
        x0 = int((c['x0'] + w * 0.2) * RENDER_SCALE)
        x1 = int((c['x1'] - w * 0.2) * RENDER_SCALE)
        y0 = int((c['top'] + h * 0.2) * RENDER_SCALE)
        y1 = int((c['bottom'] - h * 0.2) * RENDER_SCALE)
        dark = 0
        for x in range(max(x0, 0), min(max(x1, x0 + 1), width)):
            for y in range(max(y0, 0), min(max(y1, y0 + 1), height)):
                if pixels[x, y] < INK_DARK:
                    dark += 1
                    if dark >= INK_MIN_PIXELS:
                        return True
        return False

    return visible


def _letters_by_cell(page, columns, rows, visible):
    """{(day, column_index): [letter, ...]} for printed letters in the grid."""
    cells = {}
    seen = set()
    for c in page.chars:
        if not c['text'].strip():
            continue
        # Bold text is drawn twice at (almost) the same spot: keep one copy.
        key = (c['text'], round(c['x0'] * 2), round(c['top'] * 2))
        if key in seen:
            continue
        seen.add(key)
        cx, cy = (c['x0'] + c['x1']) / 2, (c['top'] + c['bottom']) / 2
        col = next((i for i, (_, _, l, r) in enumerate(columns) if l <= cx < r), None)
        day = next((d for d, (t, b) in rows.items() if t <= cy < b), None)
        if col is None or day is None or not visible(c):
            continue
        cells.setdefault((day, col), []).append(c)
    return cells


def _lines(letters):
    """A cell's letters as its lines of text, top to bottom."""
    letters = sorted(letters, key=lambda c: c['top'])
    groups, current = [], []
    for c in letters:
        # A new line starts when a letter sits well below the current line's
        # first letter. Small letters on the same line (e.g. 'AFIT-ACC212'
        # set smaller than '(L)') differ by ~2pt; real lines by ~9pt.
        if current and c['top'] - current[0]['top'] > 4:
            groups.append(current)
            current = []
        current.append(c)
    if current:
        groups.append(current)

    lines = []
    for group in groups:
        group.sort(key=lambda c: c['x0'])
        text = ''
        for prev, c in zip([None] + group[:-1], group):
            # A visible gap between letters is a space ('LR 102').
            if prev is not None and c['x0'] - prev['x1'] > c['size'] * 0.2:
                text += ' '
            text += c['text']
        text = re.sub(r'\s+', ' ', text).strip()
        if text:
            lines.append(text)
    return lines


def _merge_back_to_back(slots):
    """Join consecutive hours of the same class into one slot."""
    slots = sorted(slots, key=lambda s: (s.day, s.start))
    merged = []
    for s in slots:
        last = merged[-1] if merged else None
        if (last and last.day == s.day and last.end == s.start
                and (last.code, last.kind, last.room) == (s.code, s.kind, s.room)):
            last.end = s.end
        else:
            merged.append(ParsedSlot(s.code, s.kind, s.day, s.start, s.end, s.room))
    return merged


def _day_name(day):
    return ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][day]
