import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:suaams/core/theme/app_theme.dart';
import 'package:suaams/features/student/models/week_schedule_entry.dart';
import 'package:suaams/shared/widgets/app_stat_box.dart';
import 'package:suaams/shared/widgets/week_schedule_list.dart';

// The 11sp floor (2026-11-09) made small text bigger, so the tightest rows
// are checked on a narrow phone (360dp) at the default and a raised system
// text size. A RenderFlex overflow throws in a test, so a pump that
// completes means nothing spilled.

Future<void> _pumpAt(
  WidgetTester tester,
  Widget child, {
  required double textScale,
}) async {
  tester.view.physicalSize = const Size(360, 780);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.darkTheme,
      home: MediaQuery(
        data: MediaQueryData(
          size: const Size(360, 780),
          textScaler: TextScaler.linear(textScale),
        ),
        child: Scaffold(
          body: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: child,
          ),
        ),
      ),
    ),
  );
  expect(tester.takeException(), isNull);
}

void main() {
  for (final scale in [1.0, 1.3]) {
    testWidgets('three-across stat captions fit at 360dp, text x$scale', (
      tester,
    ) async {
      await _pumpAt(
        tester,
        const AppStatRow([
          AppStatValue('2', 'COURSES'),
          AppStatValue('0', 'LIVE NOW'),
          AppStatValue('188', 'CHECK-INS TODAY'),
        ]),
        textScale: scale,
      );
    });

    testWidgets('week rows fit at 360dp, text x$scale', (tester) async {
      await _pumpAt(
        tester,
        WeekScheduleList(
          entries: [
            WeekScheduleEntry(
              dayOfWeek: DateTime(2026, 11, 9).weekday - 1,
              courseId: 1,
              courseName: 'Introduction to Control Systems Engineering',
              courseCode: 'MCT 590',
              startTime: '10:00',
              endTime: '12:00',
              room: 'Lecture Theatre 2',
              lecturer: 'Dr Adebayo Oluwaseun',
            ),
          ],
          dayRoute: '/student/timetable/day',
          showLecturer: true,
          now: DateTime(2026, 11, 9),
        ),
        textScale: scale,
      );
    });
  }
}
