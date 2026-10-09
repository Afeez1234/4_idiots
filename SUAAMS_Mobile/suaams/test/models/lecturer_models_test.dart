// Contract tests for the lecturer-side models against the response bodies
// of SUAAMS/api/lecturer.py. Same rationale as student_models_test.dart:
// the fromJson casts are the API boundary and fail only at runtime.
//
// Each test unwraps its fixture with the same key LecturerService uses.

import 'package:flutter_test/flutter_test.dart';
import 'package:suaams/features/lecturer/models/announcement_model.dart';
import 'package:suaams/features/lecturer/models/course_analytics_model.dart';
import 'package:suaams/features/lecturer/models/course_workspace_model.dart';
import 'package:suaams/features/lecturer/models/lecturer_dashboard_model.dart';
import 'package:suaams/features/lecturer/models/session_detail_model.dart';
import 'package:suaams/features/lecturer/models/session_history_model.dart';
import 'package:suaams/features/student/models/week_schedule_entry.dart';

// Relative on purpose -- see the note in auth_models_test.dart.
import '../support/api_fixtures.dart';

void main() {
  group('LecturerDashboardModel (GET /lecturer/dashboard)', () {
    late LecturerDashboardModel m;
    setUp(() => m = LecturerDashboardModel.fromJson(
          loadApiData('lecturer_dashboard'),
        ));

    test('parses profile and stats', () {
      expect(m.profile.fullName, 'Dr. Musa Bello');
      expect(m.profile.staffId, 'STF/0042');
      // Lecturer.department is an optional relationship.
      expect(m.profile.department, isNull);
      expect(m.stats.totalCourses, 2);
      expect(m.stats.activeSessions, 1);
      expect(m.stats.todayCheckins, 18);
    });

    test('parses a course with a live session', () {
      final c = m.courses[0];
      expect(c.hasActiveSession, isTrue);
      expect(c.activeSessionId, 44);
      expect(c.avgAttendance, 72.5);
    });

    test('a course with no sessions: int 0 average, null session id', () {
      // avg_attendance is round(0, 1) == int 0 when there's nothing to
      // average -- must not trip the double field.
      final c = m.courses[1];
      expect(c.avgAttendance, 0.0);
      expect(c.hasActiveSession, isFalse);
      expect(c.activeSessionId, isNull);
    });
  });

  group('CourseWorkspaceModel (GET /lecturer/course/<id>)', () {
    test('parses a live session and its check-ins', () {
      final m = CourseWorkspaceModel.fromJson(
        loadApiData('lecturer_course_workspace_live'),
      );

      expect(m.course.code, 'MCT 401');
      expect(m.stats.presentNow, 2);
      expect(m.activeSession, isNotNull);
      expect(m.activeSession!.id, 44);
      expect(m.activeSession!.plannedStart, '09:00:00');
      expect(m.activeSession!.sessionDate, '2026-10-08');

      expect(m.liveAttendance, hasLength(2));
      final first = m.liveAttendance.first;
      // Regression: was typed int against a String column and threw the
      // first time a real student appeared in the list.
      expect(first.level, '400');
      expect(first.department, 'Mechatronics Engineering');
      expect(m.liveAttendance.last.status, 'late');
    });

    test('no running session: active_session null, empty list', () {
      final m = CourseWorkspaceModel.fromJson(
        loadApiData('lecturer_course_workspace_idle'),
      );
      expect(m.activeSession, isNull);
      expect(m.liveAttendance, isEmpty);
      expect(m.stats.avgAttendance, 0.0);
    });
  });

  group('SessionHistoryModel (GET /lecturer/course/<id>/history)', () {
    test('parses past sessions, including unscheduled ones', () {
      final m = SessionHistoryModel.fromJson(
        loadApiData('lecturer_session_history'),
      );

      expect(m.course.id, 7);
      expect(m.sessions, hasLength(2));

      final s = m.sessions.first;
      expect(s.sessionId, 41);
      expect(s.plannedStart, '09:00:00');
      expect(s.presentCount + s.absentCount, s.enrolledCount);

      expect(m.sessions.last.plannedStart, isNull);
      expect(m.sessions.last.presentCount, 0);
    });
  });

  group('SessionDetailModel (GET /lecturer/course/<id>/session/<id>)', () {
    test('parses the session and its attendance list', () {
      final m = SessionDetailModel.fromJson(
        loadApiData('lecturer_session_detail'),
      );

      expect(m.session.id, 41);
      expect(m.session.date, '07 Oct 2026');
      expect(m.stats.presentCount, 2);
      expect(m.stats.enrolledCount, 40);

      expect(m.attendance, hasLength(2));
      expect(m.attendance.first.level, '400');
      // An excused record has no tap time.
      expect(m.attendance.last.status, 'excused');
      expect(m.attendance.last.timeIn, isNull);
    });

    // The fixture above is the response shape from before manual marking.
    // The app must still read it (an old server, or deploy order slipping),
    // with the new fields falling back to safe defaults.
    test('reads a pre-manual-marking response with safe defaults', () {
      final m = SessionDetailModel.fromJson(
        loadApiData('lecturer_session_detail'),
      );

      expect(m.notCheckedIn, isEmpty);
      expect(m.session.isActive, isFalse);
      expect(m.attendance.first.method, isNull);
    });

    test('parses check-in methods and the not-checked-in list', () {
      final m = SessionDetailModel.fromJson(
        loadApiData('lecturer_session_detail_live'),
      );

      expect(m.session.isActive, isTrue);
      expect(m.attendance.map((a) => a.method), ['nfc', 'ble', 'manual']);

      expect(m.notCheckedIn, hasLength(2));
      expect(m.notCheckedIn.first.studentId, 14);
      expect(m.notCheckedIn.first.fullName, "Kelechi O'Neil");
      expect(m.notCheckedIn.first.matricNumber, 'MCT/2022/031');
    });
  });

  group('CourseAnalyticsModel (GET /lecturer/course/<id>/analytics)', () {
    test('parses summary, trend and per-student stats', () {
      final m = CourseAnalyticsModel.fromJson(
        loadApiData('lecturer_course_analytics'),
      );

      expect(m.summary.enrolledCount, 3);
      expect(m.summary.avgAttendance, 50.0);
      expect(m.trend.map((t) => t.pct), [33.3, 66.7]);

      // Backend sorts ascending by pct so at-risk students come first;
      // the 0% entry is an int 0 on the wire.
      expect(m.students.first.fullName, 'Chidi Eze');
      expect(m.students.first.pct, 0.0);
      expect(m.students.last.pct, 100.0);
    });

    test('a course with no completed sessions parses', () {
      final m = CourseAnalyticsModel.fromJson(
        loadApiData('lecturer_course_analytics_empty'),
      );
      expect(m.summary.avgAttendance, 0.0);
      expect(m.trend, isEmpty);
      expect(m.students, isEmpty);
    });
  });

  group('AnnouncementItem (GET /lecturer/announcements)', () {
    test('parses the list under data', () {
      // Unlike most lecturer endpoints, `data` here is a list, not an object.
      final items = (loadApiFixture('lecturer_announcements')['data'] as List)
          .map((e) => AnnouncementItem.fromJson(e as Map<String, dynamic>))
          .toList();

      expect(items, hasLength(1));
      expect(items.first.courseId, 7);
      expect(items.first.courseCode, 'MCT 401');
      // Pre-formatted display string on this endpoint (strftime), NOT the
      // ISO timestamp the student announcements endpoint sends.
      expect(items.first.createdAt, '06 Oct 2026, 10:00');
    });
  });

  group('WeekScheduleEntry (GET /lecturer/schedule/week)', () {
    test('the lecturer endpoint matches the shared student model', () {
      // LecturerService reuses the student-side WeekScheduleEntry; this
      // fails if the two endpoints' shapes ever drift apart.
      final week = (loadApiFixture('lecturer_schedule_week')['week'] as List)
          .map((e) => WeekScheduleEntry.fromJson(e as Map<String, dynamic>))
          .toList();

      expect(week, hasLength(2));
      expect(week[1].dayOfWeek, 4);
      expect(week[1].courseCode, 'MCT 421');
      expect(week[1].room, isNull);
    });
  });
}
