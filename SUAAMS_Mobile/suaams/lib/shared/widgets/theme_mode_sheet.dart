import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:suaams/core/providers/theme_provider.dart';

/// Interface theme chooser, shared by the student and lecturer profiles.
/// Replaces a dark/light toggle that had no way to follow the phone.
class ThemeModeSheet extends ConsumerWidget {
  const ThemeModeSheet({super.key});

  static void show(BuildContext context) {
    showModalBottomSheet(
      context: context,
      showDragHandle: true,
      builder: (_) => const ThemeModeSheet(),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final current = ref.watch(themeProvider);
    final muted = Theme.of(
      context,
    ).colorScheme.onSurface.withValues(alpha: 0.6);

    Widget option(ThemeMode mode, String subtitle) {
      return RadioListTile<ThemeMode>(
        value: mode,
        title: Text(
          themeModeLabel(mode),
          style: const TextStyle(fontWeight: FontWeight.w600),
        ),
        subtitle: Text(subtitle, style: TextStyle(fontSize: 12, color: muted)),
      );
    }

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.only(bottom: 16),
        child: RadioGroup<ThemeMode>(
          groupValue: current,
          onChanged: (mode) {
            if (mode == null) return;
            ref.read(themeProvider.notifier).set(mode);
            Navigator.pop(context);
          },
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Padding(
                padding: EdgeInsets.fromLTRB(24, 0, 24, 8),
                child: Text(
                  'INTERFACE THEME',
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                    letterSpacing: 2,
                  ),
                ),
              ),
              option(
                ThemeMode.system,
                "Matches your phone's light or dark setting.",
              ),
              option(ThemeMode.dark, 'Always dark.'),
              option(ThemeMode.light, 'Always light.'),
            ],
          ),
        ),
      ),
    );
  }
}
