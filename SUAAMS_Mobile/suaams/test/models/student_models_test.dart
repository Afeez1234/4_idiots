// Contract tests for the student-side models against the response bodies
// of SUAAMS/api/student.py.
//
// These pin the API boundary: every fromJson here does hard `as` casts, so a
// renamed key, a field that turns nullable, or an int where a double was
// expected throws a TypeError at runtime -- on a real phone, in front of a
// user -- and nothing in the analyzer catches it. (LiveAttendanceEntry.level
// shipped as `int` against a String column and was only found on-device.)
//
// Each test unwraps its fixture with the same key the real StudentService
// uses, so an envelope change fails here too.

import 'package:flutter_test/flutter_test.dart';
import 'package:suaams/features/student/models/available_course_model.dart';
import 'package:suaams/features/student/models/course_attendance_history_model.dart';
import 'package:suaams/features/student/models/device_info.dart';
import 'package:suaams/features/student/models/notification_item.dart';
import 'package:suaams/features/student/models/student_announcement_model.dart';
import 'package:suaams/features/student/models/student_dashboard_model.dart';
import 'package:suaams/features/student/models/today_protocol_entry.dart';
import 'package:suaams/features/student/models/week_schedule_entry.dart';

// Relative on purpose -- see the note in auth_models_test.dart.
import '../support/api_fixtures.dart';

/// Parses a top-level list (e.g. body['today_protocol']) the way the
/// services do: `(responseData[key] as List).map(fromJson).toList()`.
List<T> _parseList<T>(
  String fixture,
  String key,
  T Function(Map<String, dynamic>) fromJson,
) {
  return (loadApiFixture(fixture)[key] as List)
      .map((e) => fromJson(e as Map<String, dynamic>))
      .toList();
}

void main() {
  group('StudentDashboardModel (GET /student/dashboard)', () {
    test('parses a populated dashboard', () {
      final m = StudentDashboardModel.fromJson(loadApiData('student_dashboard'));

      expect(m.profile.fullName, 'Ada Okafor');
      expect(m.profile.department, 'Mechatronics Engineering');
      expect(m.profile.level, '400');
      expect(m.profile.rfidUid, isNull);
      expect(m.profile.matricNumber, 'MCT/2022/014');

      expect(m.stats.overallRate, 66.7);
      expect(m.stats.attendanceCount, 4);
      expect(m.stats.totalSessions, 6);
      expect(m.stats.atRiskCount, 3);
      expect(m.stats.enrollmentCount, 3);

      expect(m.courses, hasLength(3));
      expect(m.courses.first.code, 'MCT 401');
      expect(m.courses.first.pct, 66.7);

      expect(m.recentAttendance, hasLength(2));
      // session_id drives the tap-through into the session detail view;
      // it was once missing from this payload.
      expect(m.recentAttendance.first.sessionId, 41);
      // The backend's null-time fallback is a literal string, not null.
      expect(m.recentAttendance.last.time, '--:--');
    });

    test('Python int 0 (from round(0, 1)) parses into the double fields', () {
      // A course with no sessions yet has pct = round(0, 1) == 0, which
      // jsonify emits as the INT 0. A plain `as double` cast would throw.
      final m = StudentDashboardModel.fromJson(loadApiData('student_dashboard'));
      expect(m.courses.last.pct, 0.0);
      expect(m.courses.last.total, 0);
    });

    test('a brand-new student with no enrollments parses', () {
      final m = StudentDashboardModel.fromJson(
        loadApiData('student_dashboard_new_student'),
      );
      expect(m.stats.overallRate, 0.0);
      expect(m.courses, isEmpty);
      expect(m.recentAttendance, isEmpty);
      // The backend's own fallback when no department is linked.
      expect(m.profile.department, 'Unknown');
    });

    test('level tolerates a numeric value', () {
      // Student.level is a String column ("400") today, but the model is
      // deliberately defensive about it -- pin that so the .toString()
      // isn't "tidied" back into a cast.
      final json = loadApiData('student_dashboard');
      (json['student'] as Map<String, dynamic>)['level'] = 400;
      expect(StudentDashboardModel.fromJson(json).profile.level, '400');
    });
  });

  group('CourseAttendanceHistoryModel (GET /student/course/<id>/history)', () {
    test('parses attended and missed sessions', () {
      final m = CourseAttendanceHistoryModel.fromJson(
        loadApiData('student_course_history'),
      );

      expect(m.course.id, 7);
      expect(m.course.code, 'MCT 401');
      expect(m.sessions, hasLength(2));

      final attended = m.sessions.first;
      expect(attended.status, 'present');
      // str(time) on the backend -- seconds included, unlike strftime.
      expect(attended.plannedStart, '09:00:00');
      expect(attended.timeIn, '09:04');

      // A session with no Attendance row comes back 'absent' with no
      // time_in, and an unscheduled one has no planned times.
      final missed = m.sessions.last;
      expect(missed.status, 'absent');
      expect(missed.timeIn, isNull);
      expect(missed.plannedStart, isNull);
      expect(missed.plannedEnd, isNull);
    });
  });

  group('TodayProtocolEntry (GET /student/schedule/today)', () {
    late List<TodayProtocolEntry> entries;
    setUp(() {
      entries = _parseList(
        'student_schedule_today',
        'today_protocol',
        TodayProtocolEntry.fromJson,
      );
    });

    test('parses a scheduled, live session', () {
      final e = entries[0];
      expect(e.courseId, 7);
      expect(e.status, 'PENDING');
      expect(e.sessionLive, isTrue);
      expect(e.room, 'LT 2');
    });

    test('scheduled rows omit ad_hoc entirely and default to false', () {
      // The backend only adds 'ad_hoc' to rows from the unscheduled-session
      // loop; timetable rows don't carry the key at all.
      expect(entries[0].adHoc, isFalse);
      expect(entries[1].adHoc, isFalse);
    });

    test('PENDING with session_live false keeps the check-in disarmed', () {
      // PENDING covers both "live, not checked in" and "lecturer hasn't
      // started yet" -- session_live is the only thing that tells them apart.
      final notStarted = entries[1];
      expect(notStarted.status, 'PENDING');
      expect(notStarted.sessionLive, isFalse);
    });

    test('parses an ad-hoc session with no room or end time', () {
      final e = entries[2];
      expect(e.adHoc, isTrue);
      expect(e.sessionLive, isTrue);
      expect(e.endTime, isNull);
      expect(e.room, isNull);
    });

    test('missing session_live defaults to false (the safe direction)', () {
      // An older backend without the field must leave the card inert rather
      // than invite a check-in the server will reject.
      final e = TodayProtocolEntry.fromJson({
        'course_id': 1,
        'course_name': 'X',
        'course_code': 'X 101',
        'status': 'PENDING',
      });
      expect(e.sessionLive, isFalse);
    });
  });

  group('WeekScheduleEntry (GET /student/schedule/week)', () {
    test('parses timetable rows, including ones with no times or room', () {
      final week = _parseList(
        'student_schedule_week',
        'week',
        WeekScheduleEntry.fromJson,
      );
      expect(week, hasLength(2));
      // 0 = Monday, matching Python's date.weekday().
      expect(week[0].dayOfWeek, 0);
      expect(week[0].startTime, '09:00');
      expect(week[1].startTime, isNull);
      expect(week[1].room, isNull);
    });
  });

  group('NotificationItem (GET /student/notifications)', () {
    late List<NotificationItem> items;
    setUp(() {
      items = _parseList(
        'student_notifications',
        'notifications',
        NotificationItem.fromJson,
      );
    });

    test('parses notifications with and without a data payload', () {
      expect(items, hasLength(2));
      expect(items[0].type, 'attendance_marked');
      expect(items[0].read, isFalse);
      expect(items[0].data, {'session_id': 41, 'course_code': 'MCT 401'});
      expect(items[1].data, isNull);
      expect(items[1].read, isTrue);
    });

    test('created_at is read as UTC, not device-local time', () {
      // Regression: MySQL drops tzinfo, so the backend once sent a naive
      // ISO string and DateTime.parse read it as LOCAL time, skewing
      // "time ago" by the phone's UTC offset. The backend now appends
      // +00:00; this pins that the client honours it. Also covers
      // isoformat()'s six-digit microseconds.
      final created = items[0].createdAt;
      expect(created.isUtc, isTrue);
      expect(created, DateTime.utc(2026, 10, 7, 8, 4, 12, 512, 331));
    });
  });

  group('StudentAnnouncement (GET /student/announcements)', () {
    late List<StudentAnnouncement> items;
    setUp(() {
      items = _parseList(
        'student_announcements',
        'announcements',
        StudentAnnouncement.fromJson,
      );
    });

    test('parses each scope with only its own label populated', () {
      final course = items[0];
      expect(course.scope, 'course');
      expect(course.courseCode, 'MCT 401');
      expect(course.departmentName, isNull);

      final dept = items[1];
      expect(dept.scope, 'department');
      expect(dept.departmentName, 'Mechatronics Engineering');
      expect(dept.courseCode, isNull);

      final uni = items[2];
      expect(uni.scope, 'university');
      expect(uni.departmentName, isNull);
      expect(uni.courseCode, isNull);
    });

    test('carries the server-computed read flag', () {
      expect(items.map((a) => a.isRead), [false, true, true]);
    });

    test('missing is_read defaults to unread, never silently hidden', () {
      final a = StudentAnnouncement.fromJson({
        'id': 1,
        'title': 't',
        'body': 'b',
        'scope': 'university',
      });
      expect(a.isRead, isFalse);
    });
  });

  group('DeviceInfo (GET /student/device-info)', () {
    test('parses the binding flag', () {
      final info = DeviceInfo.fromJson(loadApiData('student_device_info'));
      expect(info.deviceBound, isTrue);
    });
  });

  group('AvailableCourse (GET /student/courses/available)', () {
    // Mirrors StudentService: responseData['data']['courses'].
    List<AvailableCourse> parse(String fixture) =>
        (loadApiData(fixture)['courses'] as List)
            .map((e) => AvailableCourse.fromJson(e as Map<String, dynamic>))
            .toList();

    test('parses courses, including unassigned lecturer and credit units', () {
      final courses = parse('student_courses_available');
      expect(courses, hasLength(2));

      expect(courses[0].courseCode, 'MCT 401');
      expect(courses[0].creditUnits, 3);
      expect(courses[0].lecturer, 'Dr. Musa Bello');
      expect(courses[0].enrolled, isTrue);

      expect(courses[1].creditUnits, isNull);
      expect(courses[1].lecturer, isNull);
      expect(courses[1].enrolled, isFalse);
    });

    test('no active semester yields an empty list, not a crash', () {
      expect(parse('student_courses_available_no_semester'), isEmpty);
    });
  });
}
