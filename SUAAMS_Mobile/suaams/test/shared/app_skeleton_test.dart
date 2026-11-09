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

  // SlowLoadHint (2026-11-01): silent for the first 5 s, then shown and
  // readable by a screen reader; no fade with reduced motion.
  Widget hintHost({required bool disableAnimations}) => MaterialApp(
    theme: AppTheme.darkTheme,
    home: MediaQuery(
      data: MediaQueryData(disableAnimations: disableAnimations),
      child: const Scaffold(body: SlowLoadHint()),
    ),
  );

  double hintOpacity(WidgetTester tester) => tester
      .widget<AnimatedOpacity>(
        find.descendant(
          of: find.byType(SlowLoadHint),
          matching: find.byType(AnimatedOpacity),
        ),
      )
      .opacity;

  testWidgets('slow-load hint waits 5 s, then shows', (tester) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(hintHost(disableAnimations: false));
    await tester.pump(const Duration(seconds: 4));
    expect(hintOpacity(tester), 0);
    expect(find.bySemanticsLabel(SlowLoadHint.message), findsNothing);

    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();
    expect(hintOpacity(tester), 1);
    expect(find.bySemanticsLabel(SlowLoadHint.message), findsOneWidget);
    handle.dispose();
  });

  testWidgets('slow-load hint appears without a fade under reduced motion', (
    tester,
  ) async {
    await tester.pumpWidget(hintHost(disableAnimations: true));
    await tester.pump(const Duration(seconds: 5));
    final fade = tester.widget<AnimatedOpacity>(
      find.descendant(
        of: find.byType(SlowLoadHint),
        matching: find.byType(AnimatedOpacity),
      ),
    );
    expect(fade.opacity, 1);
    expect(fade.duration, Duration.zero);
  });

  testWidgets('slow-load hint cancels its timer when the data arrives', (
    tester,
  ) async {
    await tester.pumpWidget(hintHost(disableAnimations: false));
    await tester.pump(const Duration(seconds: 2));
    // Data landed: the loading view is replaced. A live timer here would
    // fail the test ("A Timer is still pending").
    await tester.pumpWidget(const MaterialApp(home: SizedBox()));
    await tester.pump(const Duration(seconds: 5));
  });
}
