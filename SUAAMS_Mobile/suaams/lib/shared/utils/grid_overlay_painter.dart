// shared/utils/grid_overlay_painter.dart
import 'package:flutter/material.dart';

class GridOverlayPainter extends CustomPainter {
  final Color color;
  // PERF FIX: const constructor -- shouldRepaint always returns false below,
  // so every call site (login/change-password/splash/dashboard) can now be
  // built as `const GridOverlayPainter(...)`, letting Flutter reuse a single
  // compiled instance instead of allocating a new painter each rebuild.
  const GridOverlayPainter({required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final gridPaint = Paint()
      ..color = color.withValues(alpha: 0.03)
      ..strokeWidth = 0.4;
    const step = 28.0;
    for (double x = 0; x <= size.width; x += step) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), gridPaint);
    }
    for (double y = 0; y <= size.height; y += step) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), gridPaint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
