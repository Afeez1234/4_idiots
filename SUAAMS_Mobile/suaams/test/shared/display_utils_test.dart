// Tests for the small display helpers in lib/shared/utils/.
//
// Each exists to put one rule in exactly one place (the files' own headers
// explain why), so these pin that rule:
//  - attendanceStatusLabel/Text: the four backend statuses map to fixed
//    copy and contrast-checked colours, and anything unknown degrades to
//    ABSENT rather than throwing.
//  - formatDateLabel: the hand-rolled weekday/month lookup (no `intl`) is
//    off-by-one-prone -- DateTime.weekday and .month are both 1-based.
//  - initialOf: never throws on blank input; replaced `name[0]`, which did.

import 'package:flutter_test/flutter_test.dart';
import 'package:suaams/core/theme/app_terminal.dart';
import 'package:suaams/shared/utils/attendance_status.dart';
import 'package:suaams/shared/utils/date_label.dart';
import 'package:suaams/shared/utils/initials.dart';

void main() {
  group('attendanceStatusLabel', () {
    const cases = {
      'present': 'PRESENT',
      'late': 'LATE',
      'excused': 'EXCUSED',
      'absent': 'ABSENT',
    };
    cases.forEach((status, label) {
      test('$status -> $label', () {
        expect(attendanceStatusLabel(status), label);
      });
    });

    test('unknown or empty status falls back to ABSENT, never throws', () {
      // e.g. a new backend enum value this build doesn't know yet, or the
      // uppercase PENDING/PRESENT vocabulary of /schedule/today leaking in.
      expect(attendanceStatusLabel('mystery'), 'ABSENT');
      expect(attendanceStatusLabel(''), 'ABSENT');
      expect(attendanceStatusLabel('PRESENT'), 'ABSENT');
    });
  });

  group('attendanceStatusText', () {
    for (final (name, palette) in [
      ('dark', AppTerminal.dark),
      ('light', AppTerminal.light),
    ]) {
      test('maps each status to its $name-palette text colour', () {
        expect(attendanceStatusText('present', palette), palette.successText);
        expect(attendanceStatusText('late', palette), palette.warningText);
        expect(attendanceStatusText('excused', palette), palette.textSecondary);
        expect(attendanceStatusText('absent', palette), palette.dangerText);
        expect(attendanceStatusText('mystery', palette), palette.dangerText);
      });
    }

    test('defaults to the dark palette when none is passed', () {
      expect(attendanceStatusText('present'), AppTerminal.dark.successText);
    });

    test('text colours are the contrast-checked ones, not the raw hues', () {
      // The raw AppStatus hues fail WCAG AA as text on the light theme
      // (see AppStatus's doc comment); a light-mode label must never get one.
      final light = AppTerminal.light;
      expect(attendanceStatusText('present', light), isNot(AppStatus.success));
      expect(attendanceStatusText('late', light), isNot(AppStatus.warning));
      expect(attendanceStatusText('absent', light), isNot(AppStatus.danger));
    });
  });

  group('formatDateLabel', () {
    test('formats the documented example', () {
      expect(
        formatDateLabel(DateTime(2026, 9, 28)),
        'Monday, 28 September 2026',
      );
    });

    test('every weekday maps correctly, including Sunday (weekday 7)', () {
      // 2026-09-28 is a Monday; walk the following seven days.
      const expected = [
        'Monday',
        'Tuesday',
        'Wednesday',
        'Thursday',
        'Friday',
        'Saturday',
        'Sunday',
      ];
      for (var i = 0; i < 7; i++) {
        final label = formatDateLabel(DateTime(2026, 9, 28 + i));
        expect(label, startsWith('${expected[i]},'));
      }
    });

    test('January and December hit both ends of the month table', () {
      expect(formatDateLabel(DateTime(2027, 1, 1)), 'Friday, 1 January 2027');
      expect(
        formatDateLabel(DateTime(2026, 12, 31)),
        'Thursday, 31 December 2026',
      );
    });

    test('day is not zero-padded', () {
      expect(formatDateLabel(DateTime(2026, 10, 8)), 'Thursday, 8 October 2026');
    });

    test('todayLabel agrees with formatDateLabel(now)', () {
      // Can straddle midnight in theory; compared both ways round so a
      // one-in-86,400 flake can't happen.
      final before = formatDateLabel(DateTime.now());
      final label = todayLabel();
      final after = formatDateLabel(DateTime.now());
      expect([before, after], contains(label));
    });
  });

  group('initialOf', () {
    test('first letter, uppercased', () {
      expect(initialOf('ada okafor'), 'A');
      expect(initialOf('Musa Bello'), 'M');
    });

    test('leading whitespace is ignored', () {
      expect(initialOf('   chidi'), 'C');
    });

    test('null, empty and whitespace-only use the fallback', () {
      expect(initialOf(null), '?');
      expect(initialOf(''), '?');
      expect(initialOf('   '), '?');
    });

    test('a custom fallback is honoured', () {
      expect(initialOf('', fallback: 'S'), 'S');
    });

    test('non-ASCII first letters uppercase correctly', () {
      expect(initialOf('élise'), 'É');
    });
  });
}
