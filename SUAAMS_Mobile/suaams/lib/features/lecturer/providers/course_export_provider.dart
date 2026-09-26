import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:suaams/core/network/auth_retry.dart';
import 'package:suaams/features/lecturer/providers/lecturer_provider.dart';

// Which course (if any) is currently being exported -- drives the per-card
// spinner and blocks double taps while a download is in flight.
final courseExportProvider =
    NotifierProvider.autoDispose<CourseExportNotifier, int?>(
      CourseExportNotifier.new,
    );

class CourseExportNotifier extends Notifier<int?> {
  @override
  int? build() => null;

  // Downloads the register CSV, writes it to the app's temp directory and
  // opens the OS share sheet (save to Files/Drive, email, WhatsApp...).
  // Returns an error message, or null on success -- the caller shows the
  // SnackBar. Temp dir means no storage permissions are needed.
  Future<String?> exportRegister(int courseId, String courseCode) async {
    if (state != null) return null;
    state = courseId;

    try {
      final service = ref.read(lecturerServiceProvider);
      final bytes = await withAuthRetry(
        ref,
        (token) => service.downloadCourseRegister(token, courseId),
      );

      final dir = await getTemporaryDirectory();
      final safeCode = courseCode.replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '_');
      final file = File('${dir.path}/${safeCode}_attendance_register.csv');
      await file.writeAsBytes(bytes, flush: true);

      await SharePlus.instance.share(
        ShareParams(
          files: [XFile(file.path, mimeType: 'text/csv')],
          subject: '$courseCode attendance register',
        ),
      );
      return null;
    } catch (e) {
      return e.toString().replaceAll('Exception: ', '');
    } finally {
      if (ref.mounted) state = null;
    }
  }
}
