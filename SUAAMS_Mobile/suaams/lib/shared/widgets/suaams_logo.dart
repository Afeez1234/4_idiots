import 'package:flutter/material.dart';

/// The SUAAMS mark: a flowing figure whose head is an NFC "tap" dot, with
/// two signal arcs radiating from it -- a person announcing "I'm here".
///
/// Adopted 2026-10-08 (candidate C of the icon study), replacing the
/// shield-and-waves mark. The geometry is on a 48-unit grid and MUST stay
/// identical to the `suaams_mark` macro in SUAAMS/templates/_macros.html,
/// which draws the same mark for the web dashboard. Change one, change both.
///
/// [color] is the figure (follows the surface: white on dark, black on
/// light). [accentColor] is the dot and arcs, and stays brand blue
/// everywhere -- deliberately not red, which the app uses for errors.
class SuaamsLogo extends StatelessWidget {
  final double size;
  final Color color;
  final Color accentColor;

  const SuaamsLogo({
    super.key,
    this.size = 48,
    this.color = Colors.white,
    this.accentColor = suaamsBrandBlue,
  });

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: Size(size, size),
      painter: _LogoPainter(color: color, accentColor: accentColor),
    );
  }
}

/// Brand blue -- the web dashboard's --color-accent (#2F6BEE).
const Color suaamsBrandBlue = Color(0xFF2F6BEE);

class _LogoPainter extends CustomPainter {
  final Color color;
  final Color accentColor;

  // PERF FIX: const constructor -- shouldRepaint only compares colours, so
  // this can be reused instead of allocated fresh on every SuaamsLogo build.
  const _LogoPainter({required this.color, required this.accentColor});

  @override
  void paint(Canvas canvas, Size size) {
    final s = size.width / 48;

    // Figure: two strokes. The left one is a "u" whose right arm rises
    // into the body; the right one rises and arches over into the leg.
    final figurePaint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3.4 * s
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;

    final left = Path()
      ..moveTo(9.5 * s, 29.5 * s)
      ..cubicTo(7 * s, 33.5 * s, 8 * s, 39.5 * s, 13 * s, 40.5 * s)
      ..cubicTo(18.5 * s, 41.5 * s, 22 * s, 33 * s, 26 * s, 22.5 * s);
    canvas.drawPath(left, figurePaint);

    final right = Path()
      ..moveTo(19.5 * s, 41 * s)
      ..cubicTo(23 * s, 33.5 * s, 26 * s, 26 * s, 32 * s, 23.8 * s)
      ..cubicTo(37.5 * s, 21.8 * s, 40.5 * s, 27.5 * s, 39 * s, 37 * s);
    canvas.drawPath(right, figurePaint);

    // Head = NFC dot, with the signal arcs centred on it, sweeping a
    // quarter turn from straight up round to the right.
    final head = Offset(30.5 * s, 15.5 * s);

    canvas.drawCircle(head, 3 * s, Paint()..color = accentColor);

    final arcPaint = Paint()
      ..color = accentColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.2 * s
      ..strokeCap = StrokeCap.round;
    const start = -1.37; // radians; just right of straight up
    const sweep = 1.57; // a quarter turn, clockwise
    canvas.drawArc(
      Rect.fromCircle(center: head, radius: 5.7 * s),
      start,
      sweep,
      false,
      arcPaint,
    );
    canvas.drawArc(
      Rect.fromCircle(center: head, radius: 9.1 * s),
      start,
      sweep,
      false,
      arcPaint..color = accentColor.withValues(alpha: 0.5),
    );
  }

  @override
  bool shouldRepaint(covariant _LogoPainter oldDelegate) =>
      oldDelegate.color != color || oldDelegate.accentColor != accentColor;
}

class SuaamsLogoFull extends StatelessWidget {
  final double size;
  final Color color;

  const SuaamsLogoFull({super.key, this.size = 64, this.color = Colors.white});

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SuaamsLogo(size: size, color: color),
        const SizedBox(height: 16),
        Text(
          'SUAAMS',
          style: TextStyle(
            fontSize: 28,
            fontWeight: FontWeight.w700,
            color: color,
            letterSpacing: 6.0,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          'SECURE ATTENDANCE TERMINAL',
          style: TextStyle(
            fontSize: 9,
            fontWeight: FontWeight.bold,
            letterSpacing: 2.5,
            color: color.withValues(alpha: 0.5),
          ),
        ),
      ],
    );
  }
}
