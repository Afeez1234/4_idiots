import 'package:flutter/material.dart';

class SuaamsLogo extends StatelessWidget {
  final double size;
  final Color color;

  const SuaamsLogo({
    super.key,
    this.size = 48,
    this.color = Colors.white,
  });

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: Size(size, size),
      painter: _LogoPainter(color: color),
    );
  }
}

class _LogoPainter extends CustomPainter {
  final Color color;

  _LogoPainter({required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final s = size.width / 48;
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5 * s
      ..strokeCap = StrokeCap.round;

    // Shield path
    final shieldPath = Path()
      ..moveTo(24 * s, 6 * s)
      ..lineTo(10 * s, 12 * s)
      ..lineTo(10 * s, 24 * s)
      ..cubicTo(10 * s, 31.73 * s, 16.27 * s, 38.92 * s, 24 * s, 41 * s)
      ..cubicTo(31.73 * s, 38.92 * s, 38 * s, 31.73 * s, 38 * s, 24 * s)
      ..lineTo(38 * s, 12 * s)
      ..close();
    canvas.drawPath(shieldPath, paint);

    // NFC inner arc (left)
    paint.color = color;
    canvas.drawArc(
      Rect.fromCenter(center: Offset(24 * s, 24 * s), width: 10 * s, height: 10 * s),
      2.36, 1.57, false, paint,
    );

    // NFC outer arc (left)
    paint.color = color.withValues(alpha: 0.5);
    canvas.drawArc(
      Rect.fromCenter(center: Offset(24 * s, 24 * s), width: 18 * s, height: 18 * s),
      2.36, 1.57, false, paint,
    );

    // Center dot
    paint
      ..style = PaintingStyle.fill
      ..color = color;
    canvas.drawCircle(Offset(24 * s, 24 * s), 2 * s, paint);

    // NFC inner arc (right)
    paint
      ..style = PaintingStyle.stroke
      ..color = color;
    canvas.drawArc(
      Rect.fromCenter(center: Offset(24 * s, 24 * s), width: 10 * s, height: 10 * s),
      5.50, 1.57, false, paint,
    );

    // NFC outer arc (right)
    paint.color = color.withValues(alpha: 0.5);
    canvas.drawArc(
      Rect.fromCenter(center: Offset(24 * s, 24 * s), width: 18 * s, height: 18 * s),
      5.50, 1.57, false, paint,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}


class SuaamsLogoFull extends StatelessWidget {
  final double size;
  final Color color;

  const SuaamsLogoFull({
    super.key,
    this.size = 64,
    this.color = Colors.white,
  });

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
            fontWeight: FontWeight.w900,
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