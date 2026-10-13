"""Build look-alike timetable PDFs for tests/test_timetable_pdf.py.

The real Student Affairs sheets name real lecturers, and this repository is
public, so they are not committed (put real ones in private/ next to this
file -- it is git-ignored -- and the tests use them too). This writes PDFs in
the same layout with invented institute, course codes, rooms and names.

It copies the quirks timetable_pdf.py has to cope with in the real files:
  * every letter placed on its own, with a cell's two lines interleaved;
  * bold letters drawn twice at the same spot;
  * a code prefix set smaller and slightly higher than the rest ('XYZ-');
  * leftover text that is in the file but NOT printed -- one covered by a
    white box, one drawn in invisible text mode -- which must be ignored.

Written by hand (no PDF library) so the tests need nothing extra installed.
"""

WIDTH, HEIGHT = 841.8, 595.2          # A4 landscape, like the real sheets
HOURS = list(range(8, 18))            # 0800:0900 .. 1700:1800
DAYS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']
COL0, COL_W = 130, 60                 # first hour column's left edge, width
ROW0, ROW_H = 123.4, 23.4             # first day row's top, height (top-down y)

# What the sample prints: (day, hour, code, kind, room). Hours run
# back-to-back where a class is longer than one hour.
PRINTED = [
    (0, 8, 'XYZ-SAM101', 'L', 'LR 1'), (0, 9, 'XYZ-SAM101', 'L', 'LR 1'),
    (0, 10, 'SAM102', 'P', 'LAB A'),
    (0, 11, 'SAM102', 'L', 'LAB A'),
    (1, 13, 'SAM103', 'L', 'HALL B'), (1, 14, 'SAM103', 'T', 'HALL B'),
    (2, 15, 'GEN201', 'L', 'MAIN HALL'), (2, 16, 'GEN201', 'L', 'MAIN HALL'),
    (3, 8, 'SAM104', 'L', 'LR 2'),
]
# In the file, never on the page.
HIDDEN_UNDER_WHITE = (4, 15, 'HID999', 'L', 'GHOST ROOM')
HIDDEN_INVISIBLE = (5, 9, 'FOS', None, 'LR2')

EXPECTED = [  # what the reader must return, after joining back-to-back hours
    (0, '08:00-10:00', 'XYZ-SAM101', 'L', 'LR 1'),
    (0, '10:00-11:00', 'SAM102', 'P', 'LAB A'),
    (0, '11:00-12:00', 'SAM102', 'L', 'LAB A'),
    (1, '13:00-14:00', 'SAM103', 'L', 'HALL B'),
    (1, '14:00-15:00', 'SAM103', 'T', 'HALL B'),
    (2, '15:00-17:00', 'GEN201', 'L', 'MAIN HALL'),
    (3, '08:00-09:00', 'SAM104', 'L', 'LR 2'),
]
HEADER = ('Sample Studies', 300, 'Second Semester 2025/2026')


# Helvetica letter widths (per 1000 units of font size), from its standard
# metrics. Letters are placed by their real widths, as the real files do --
# evenly spaced letters leave gaps after narrow ones (I, 1) that the reader
# would rightly take for spaces.
_WIDTHS = {**{c: 667 for c in 'ABEKPSVXY'}, **{c: 722 for c in 'CDHNRU'},
           **{c: 611 for c in 'FTZ'}, **{c: 778 for c in 'GOQ'}, 'I': 278, 'J': 500,
           'L': 556, 'M': 833, 'W': 944, **{c: 556 for c in '0123456789'},
           '(': 333, ')': 333, '-': 333, ' ': 278, '.': 278, '/': 278, ',': 278, ':': 278}


def _advance(ch, size):
    return _WIDTHS.get(ch, 556) * size / 1000


def _esc(text):
    return text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


class _Page:
    def __init__(self):
        self.ops = []

    def text(self, s, x, top, size=9.5, mode=0, bold=False):
        """Each letter as its own text object; `top` measured from the page
        top, like pdfplumber reports it."""
        y = HEIGHT - top - size * 0.8
        cx = x
        for ch in s:
            copies = 2 if bold and ch.strip() else 1
            for _ in range(copies):
                self.ops.append(f'BT {mode} Tr /F1 {size} Tf {cx:.2f} {y:.2f} Td ({_esc(ch)}) Tj ET')
            cx += _advance(ch, size)

    def letters(self, s, x, top, size=9.5, bold=False):
        """Per-letter text objects, returned rather than emitted, so two
        lines can be interleaved."""
        y = HEIGHT - top - size * 0.8
        out = []
        cx = x
        for ch in s:
            for _ in range(2 if bold and ch.strip() else 1):
                out.append(f'BT 0 Tr /F1 {size} Tf {cx:.2f} {y:.2f} Td ({_esc(ch)}) Tj ET')
            cx += _advance(ch, size)
        return out

    def line(self, x0, top0, x1, top1):
        self.ops.append(f'0 G 0.8 w {x0:.2f} {HEIGHT - top0:.2f} m {x1:.2f} {HEIGHT - top1:.2f} l S')

    def white_box(self, x0, top, x1, bottom):
        self.ops.append(f'1 g {x0:.2f} {HEIGHT - bottom:.2f} {x1 - x0:.2f} {bottom - top:.2f} re f 0 g')

    def stream(self):
        return '\n'.join(self.ops).encode('latin-1')


def _cell(page, day, hour, code, kind, room, bold=False, mode=0):
    x = COL0 + (hour - 8) * COL_W + 3
    top = ROW0 + day * ROW_H + 3
    if kind is None:  # a room on its own, like the real "FOS LR2"
        page.text(f'{code} {room}', x, top + 2, size=8, mode=mode)
        return
    code_ops = []
    if code.startswith('XYZ-'):          # smaller, slightly higher prefix
        prefix_w = sum(_advance(ch, 6) for ch in 'XYZ-')
        code_ops += page.letters('XYZ-', x, top - 2, size=6)
        code_ops += page.letters(code[4:] + f'({kind})', x + prefix_w, top, size=8, bold=bold)
    else:
        code_ops += page.letters(f'{code}({kind})', x, top, size=8, bold=bold)
    room_ops = page.letters(room, x, top + 9, size=8)
    # Interleave the two lines, the way the real files store them.
    mixed = []
    for i in range(max(len(code_ops), len(room_ops))):
        mixed += code_ops[i:i + 1] + room_ops[i:i + 1]
    if mode:
        mixed = [op.replace('BT 0 Tr', f'BT {mode} Tr') for op in mixed]
    page.ops += mixed


def _build_page():
    p = _Page()
    title = [('SAMPLE INSTITUTE OF TECHNOLOGY', 11), ('FACULTY OF EXAMPLES', 29),
             ('DEPARTMENT OF SAMPLE STUDIES', 47),
             ('SECOND SEMESTER 2025/2026 SESSION LECTURE TIMETABLE', 65),
             ('300 LEVEL B.SC. - SAMPLE STUDIES', 83)]
    for text, top in title:
        p.text(text, 240, top, size=11)
    p.text('DAY', 82, 112.8, size=9)
    for i, h in enumerate(HOURS):
        p.text(f'{h:02d}00:{h + 1:02d}00', COL0 + i * COL_W + 6, 112.8, size=9)
    for d, name in enumerate(DAYS):
        p.text(name, 76, ROW0 + d * ROW_H + 9, size=9)
    # Grid lines.
    right = COL0 + len(HOURS) * COL_W
    for r in range(len(DAYS) + 1):
        p.line(70, ROW0 + r * ROW_H, right, ROW0 + r * ROW_H)
    for c in range(len(HOURS) + 1):
        p.line(COL0 + c * COL_W, 105, COL0 + c * COL_W, ROW0 + len(DAYS) * ROW_H)

    for i, slot in enumerate(PRINTED):
        _cell(p, *slot, bold=(i % 3 == 0))

    # Leftover 1: in the file, then covered by a white box.
    d, h = HIDDEN_UNDER_WHITE[0], HIDDEN_UNDER_WHITE[1]
    _cell(p, *HIDDEN_UNDER_WHITE)
    p.white_box(COL0 + (h - 8) * COL_W + 2, ROW0 + d * ROW_H + 1,
                COL0 + (h - 7) * COL_W - 2, ROW0 + (d + 1) * ROW_H - 1)
    # Leftover 2: drawn in invisible text mode (3 Tr).
    _cell(p, *HIDDEN_INVISIBLE, mode=3)

    p.text('LEGEND', 46, 274.7, size=9)
    p.text('SAM101 Example Course One - Dr A. Example', 52, 300, size=9)
    return p


def build_pdf(pages=1):
    """PDF bytes: the sample sheet, repeated over `pages` pages."""
    content = _build_page().stream()
    objs = ['<< /Type /Catalog /Pages 2 0 R >>']
    kids = ' '.join(f'{4 + 2 * i} 0 R' for i in range(pages))
    objs.append(f'<< /Type /Pages /Kids [{kids}] /Count {pages} >>')
    objs.append('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    for i in range(pages):
        objs.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {WIDTH} {HEIGHT}] '
                    f'/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>')
        objs.append(None)  # content stream, written below

    out = bytearray(b'%PDF-1.4\n')
    offsets = []
    for n, obj in enumerate(objs, start=1):
        offsets.append(len(out))
        if obj is None:
            out += f'{n} 0 obj\n<< /Length {len(content)} >>\nstream\n'.encode() + content + b'\nendstream\nendobj\n'
        else:
            out += f'{n} 0 obj\n{obj}\nendobj\n'.encode()
    xref = len(out)
    out += f'xref\n0 {len(objs) + 1}\n0000000000 65535 f \n'.encode()
    for off in offsets:
        out += f'{off:010d} 00000 n \n'.encode()
    out += f'trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    return bytes(out)


if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else 'sample_timetable.pdf'
    with open(path, 'wb') as f:
        f.write(build_pdf())
    print(f'wrote {path}')
