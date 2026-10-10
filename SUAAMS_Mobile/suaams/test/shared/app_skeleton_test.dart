import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:suaams/core/theme/app_theme.dart';
import 'package:suaams/shared/widgets/app_skeleton.dart';

// Covers the two behaviours of SkeletonPulse that are easy to break without
// noticing: it must animate normally, and it must hold still when the
// system asks for reduced motion.

Widget _host({required bool disableAnimations}) {
  return MaterialApp(
    theme: AppTheme.darkTheme,
    home: MediaQuery(
      data: MediaQueryData(disableAnimations: disableAnimations),
      child: const Scaffold(body: SkeletonList(count: 2)),
    ),
  );
}

double _opacity(WidgetTester tester) => tester
    .widget<FadeTransition>(
      find.descendant(
        of: find.byType(SkeletonPulse),
        matching: find.byType(FadeTransition),
      ),
    )
    .opacity
    .value;

void main() {
  testWidgets('pulses while loading', (tester) async {
    await tester.pumpWidget(_host(disableAnimations: false));
    final start = _opacity(tester);
    await tester.pump(const Duration(milliseconds: 450));
    expect(_opacity(tester), isNot(start));
    expect(find.byType(SkeletonListCard), findsNWidgets(2));
  });

  testWidgets('holds still with reduced motion', (tester) async {
    await tester.pumpWidget(_host(disableAnimations: true));
    final start = _opacity(tester);
    await tester.pump(const Duration(milliseconds: 450));
    expect(_opacity(tester), start);
    // pumpAndSettle would time out if a repeating animation were running.
    await tester.pumpAndSettle();
  });

  testWidgets('announces itself once to screen readers', (tester) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(_host(disableAnimations: true));
    expect(find.bySemanticsLabel('Loading'), findsOneWidget);
    handle.dispose();
  });
}
