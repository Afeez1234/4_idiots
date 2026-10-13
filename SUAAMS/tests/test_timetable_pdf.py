"""Tests for timetable_pdf.py, the Student Affairs timetable PDF reader.

Two parts:
  * the reading rules on hand-made letters -- rebuilding a cell's two lines
    from scattered letters, recognising codes, joining back-to-back hours --
    which need no PDF;
  * a look-alike sheet built by tests/fixtures/timetables/make_sample.py,
    with invented codes and names (the real sheets name real lecturers and
    this repository is public). It copies the real files' quirks, including
    text that is in the file but not printed, which must be ignored. A
    two-page version must be refused;
  * the real sheets, if you've put them in tests/fixtures/timetables/private/
    (git-ignored). Skipped when they aren't there, e.g. on GitHub.

Run with:  python tests/test_timetable_pdf.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest
from datetime import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from timetable_pdf import (  # noqa: E402
    ParsedSlot, TimetablePdfError, _CODE_LINE, _lines, _merge_back_to_back,
    normalize_code, parse_timetable_pdf,
)

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'timetables')
sys.path.insert(0, FIXTURES)
import make_sample  # noqa: E402

# Real Student Affairs sheets, kept out of git (see private/.gitignore).
ONE_PAGE = os.path.join(FIXTURES, 'private', 'acc200_one_page.pdf')
FOUR_PAGES = os.path.join(FIXTURES, 'private', 'acc200_four_pages.pdf')


def letter(text, x0, top, size=9.5):
    return {'text': text, 'x0': x0, 'x1': x0 + size * 0.5, 'top': top,
            'bottom': top + size, 'size': size}


def word(text, x0, top, size=9.5):
    out, x = [], x0
    for ch in text:
        out.append(letter(ch, x, top, size))
        x += size * 0.5
    return out


class ReadingRulesTestCase(unittest.TestCase):

    def test_cell_lines_rebuilt_from_interleaved_letters(self):
        # Code on one line, room ~9pt below; letters arrive mixed together,
        # the way the real PDFs store them.
        code = word('ACC204(L)', 100, 128)
        room = word('HALL', 100, 137.7) + word('C3', 100 + 4 * 4.75 + 3, 137.7)
        mixed = [c for pair in zip(code, room) for c in pair] + code[len(room):]
        self.assertEqual(_lines(mixed), ['ACC204(L)', 'HALL C3'])

    def test_smaller_prefix_stays_on_the_same_line(self):
        # 'AFIT-ACC212' is printed smaller and ~2pt higher than '(L)'.
        small = word('AFIT-ACC212', 100, 126.8, size=7)
        big = word('(L)', 100 + 11 * 3.5, 128.8)
        self.assertEqual(_lines(small + big), ['AFIT-ACC212(L)'])

    def test_codes_and_kinds(self):
        for text, code, kind in [('AFIT-ACC212(L)', 'AFIT-ACC212', 'L'),
                                 ('ACC204(T)', 'ACC204', 'T'),
                                 ('GST 212 (P)', 'GST 212', 'P')]:
            m = _CODE_LINE.match(text)
            self.assertEqual((m.group(1), m.group(2)), (code, kind))
        self.assertIsNone(_CODE_LINE.match('FOS LR2'))        # a room, not a class
        self.assertEqual(normalize_code('acc 206'), 'ACC206')

    def test_back_to_back_hours_join_but_different_classes_do_not(self):
        def slot(h, code='ACC212', kind='L', room='LR 102'):
            return ParsedSlot(code, kind, 0, time(h), time(h + 1), room)
        merged = _merge_back_to_back([slot(9), slot(8), slot(10, kind='T'), slot(12)])
        self.assertEqual([(s.start.hour, s.end.hour, s.kind) for s in merged],
                         [(8, 10, 'L'), (10, 11, 'T'), (12, 13, 'L')])


class LookAlikeSheetTestCase(unittest.TestCase):
    """Runs everywhere, GitHub included: the generated look-alike."""

    def test_reads_exactly_what_is_printed(self):
        import io
        sheet = parse_timetable_pdf(io.BytesIO(make_sample.build_pdf()))
        self.assertEqual((sheet.department, sheet.level, sheet.semester), make_sample.HEADER)
        got = [(s.day, f'{s.start:%H:%M}-{s.end:%H:%M}', s.code, s.kind, s.room) for s in sheet.slots]
        self.assertEqual(got, make_sample.EXPECTED)
        self.assertEqual(sheet.warnings, [])

    def test_leftovers_are_in_the_file_but_not_read(self):
        # Keeps the test above honest: the hidden entries really are in the
        # text layer, so passing means the reader skipped them, not that the
        # generator forgot to write them.
        import io
        import pdfplumber
        from timetable_pdf import _lines
        data = make_sample.build_pdf()
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            chars = pdf.pages[0].chars

        def text_layer(day, hour):
            x0 = make_sample.COL0 + (hour - 8) * make_sample.COL_W
            t0 = make_sample.ROW0 + day * make_sample.ROW_H
            return _lines([c for c in chars if c['text'].strip()
                           and x0 <= c['x0'] < x0 + make_sample.COL_W
                           and t0 <= c['top'] < t0 + make_sample.ROW_H])

        self.assertEqual(text_layer(4, 15), ['HID999(L)', 'GHOST ROOM'])   # under a white box
        self.assertEqual(text_layer(5, 9), ['FOS LR2'])                      # invisible text mode
        read = parse_timetable_pdf(io.BytesIO(data))
        self.assertNotIn('HID999', {s.code for s in read.slots})
        self.assertFalse([w for w in read.warnings if 'FOS' in w])

    def test_more_than_one_page_is_refused(self):
        import io
        with self.assertRaises(TimetablePdfError) as ctx:
            parse_timetable_pdf(io.BytesIO(make_sample.build_pdf(pages=2)))
        self.assertIn('ONE landscape page', str(ctx.exception))


@unittest.skipUnless(os.path.exists(ONE_PAGE), 'real timetable sheet not in tests/fixtures/timetables/private/')
class RealSheetTestCase(unittest.TestCase):
    """Your real Student Affairs sheet, when present on this machine."""

    def test_reads_exactly_what_is_printed(self):
        sheet = parse_timetable_pdf(ONE_PAGE)
        self.assertEqual((sheet.department, sheet.level, sheet.semester),
                         ('Accounting', 200, 'Second Semester 2025/2026'))
        got = [(s.day, f'{s.start:%H:%M}-{s.end:%H:%M}', s.code, s.kind, s.room) for s in sheet.slots]
        self.assertEqual(got, [
            (0, '08:00-10:00', 'AFIT-ACC212', 'L', 'LR 102'),
            (0, '10:00-11:00', 'ACC206', 'P', 'ICT CENTRE'),
            (0, '11:00-12:00', 'ACC206', 'L', 'ICT CENTRE'),
            (0, '13:00-14:00', 'ACC204', 'L', 'HALL C3'),
            (0, '14:00-15:00', 'ACC204', 'T', 'HALL C3'),
            (1, '08:00-10:00', 'AFIT-ACC214', 'L', 'LR 303'),
            (1, '10:00-12:00', 'ACC202', 'L', 'LR 303'),
            (1, '12:00-13:00', 'ACC202', 'T', 'LR 303'),
            (1, '15:00-17:00', 'GST212', 'L', 'ALFA HALL'),
            (3, '08:00-10:00', 'AFIT-ACC210', 'L', 'LR 303'),
            (3, '10:00-11:00', 'ACC204', 'L', 'LR 303'),
        ])
        # The text layer also holds "BUS208(L) EED HALL" (Wed) and
        # "FOS LR2" (Fri), which are NOT printed. Neither may appear.
        self.assertNotIn('BUS208', {s.code for s in sheet.slots})
        self.assertEqual(sheet.warnings, [])

    def test_reads_from_an_uploaded_file_object(self):
        with open(ONE_PAGE, 'rb') as f:
            self.assertEqual(len(parse_timetable_pdf(f).slots), 11)

    @unittest.skipUnless(os.path.exists(FOUR_PAGES), 'four-page sample not present')
    def test_four_page_export_is_refused(self):
        with self.assertRaises(TimetablePdfError) as ctx:
            parse_timetable_pdf(FOUR_PAGES)
        self.assertIn('ONE landscape page', str(ctx.exception))


class BadFileTestCase(unittest.TestCase):

    def test_not_a_pdf(self):
        import io
        with self.assertRaises(TimetablePdfError):
            parse_timetable_pdf(io.BytesIO(b'this is not a pdf'))


if __name__ == '__main__':
    unittest.main()
