import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:suaams/core/theme/app_theme.dart';
import 'package:suaams/features/student/models/week_schedule_entry.dart';
import 'package:suaams/shared/widgets/week_schedule_list.dart';

// The shared week (2026-11-01): it starts at today, a day with classes
// shows each class's time and room, and Home's "Next:" line finds the
// first class after today, wrapping past Sunday.

WeekScheduleEntry _entry(int day, String code, String start, {String? room}) =>
    WeekScheduleEntry(
      dayOfWeek: day,
      courseId: day,
      courseName: 'Course $code',
      courseCode: code,
      startTime: start,
      endTime: '12:00',
      room: room,
      lecturer: 'Dr Ade',
    );

// Sunday 1 November 2026, the day the old layout put today last.
final _sunday = DateTime(2026, 11, 1, 9);

void main() {
  final week = [
    _entry(4, 'MCT 402', '10:00', room: 'LT2'), // Friday
    _entry(5, 'MCT 402', '08:00'), // Saturday
    _entry(4, 'MCT 590', '08:00'), // Friday, earlier
  ];

  testWidgets('starts at today and lists times and rooms', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.darkTheme,
        home: Scaffold(
          body: SingleChildScrollView(
            child: WeekScheduleList(
              entries: week,
              dayRoute: '/student/timetable/day',
              showLecturer: true,
              now: _sunday,
            ),
          ),
        ),
      ),
    );

    final today = tester.getTopLeft(find.text('Today · Sunday')).dy;
    final tomorrow = tester.getTopLeft(find.text('Tomorrow · Monday')).dy;
    final friday = tester.getTopLeft(find.text('Friday')).dy;
    expect(today < tomorrow && tomorrow < friday, isTrue);

    // Friday's classes in start order, with time, room and lecturer.
    final early = tester.getTopLeft(find.text('MCT 590')).dy;
    final late = tester.getTopLeft(find.text('MCT 402').first).dy;
    expect(early < late, isTrue);
    expect(find.text('10:00–12:00'), findsOneWidget);
    expect(find.text('LT2 · Dr Ade'), findsOneWidget);

    // Five empty days, each one line.
    expect(find.text('No classes'), findsNWidgets(5));
  });

  test('next class after today is the earliest on the next class day', () {
    final next = nextClassAfterToday(week, _sunday)!;
    expect(next.courseCode, 'MCT 590');
    expect(next.dayOfWeek, 4);
  });

  test('next class wraps past Sunday', () {
    final saturday = DateTime(2026, 11, 7, 9);
    final next = nextClassAfterToday([_entry(0, 'MCT 401', '09:00')], saturday);
    expect(next?.courseCode, 'MCT 401');
  });

  test('no next class when the week is empty', () {
    expect(nextClassAfterToday(const [], _sunday), isNull);
  });
}
