import 'package:flutter/material.dart';

/// What a [AppStateView] is describing.
enum AppStateKind {
  /// Nothing to show, and that's correct -- no courses assigned yet, no
  /// records this semester. Retrying won't help.
  empty,

  /// The fetch failed. The user is probably standing at a door on a bad
  /// signal, so this one always gets a way out.
  error,
}

/// The empty / error state that used to be a bare grey `Text`.
///
/// Eleven screens had the identical `Center(child: Text(errorMessage ??
/// 'No data available'))` and about a dozen more had an unadorned grey
/// sentence in the middle of a list. None of them offered a way forward,
/// which is worst exactly where it matters most: a student standing at a
/// terminal on a bad connection, told "could not load" with no retry and
/// no indication whether their data is simply absent or unreachable.
///
/// Pass [onRetry] on anything of kind [AppStateKind.error] — a dead end
/// with no recovery is the thing this component exists to prevent.
class AppStateView extends StatelessWidget {
  final AppStateKind kind;
  final IconData icon;
  final String title;
  final String? message;
  final VoidCallback? onRetry;

  /// Smaller padding and type, for a state that sits inside a list or a
  /// card rather than owning the screen.
  final bool compact;

  const AppStateView({
    super.key,
    required this.kind,
    required this.icon,
    required this.title,
    this.message,
    this.onRetry,
    this.compact = false,
  });

  bool get _isError => kind == AppStateKind.error;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

    // Errors take the theme's error colour; an empty state stays neutral.
    // Colour alone isn't the signal though -- the icon and the presence of
    // a retry button are, so this still reads correctly to someone who
    // can't distinguish red from grey.
    final accent = _isError ? colorScheme.error : colorScheme.onSurface;
    final glyphSize = compact ? 28.0 : 36.0;
    final bubble = compact ? 48.0 : 64.0;

    return Center(
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: 32,
          vertical: compact ? 24 : 48,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: bubble,
              height: bubble,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: accent.withValues(alpha: _isError ? 0.12 : 0.07),
              ),
              child: Icon(
                icon,
                size: glyphSize,
                color: accent.withValues(alpha: 0.75),
              ),
            ),
            SizedBox(height: compact ? 12 : 16),
            Text(
              title,
              textAlign: TextAlign.center,
              style: (compact ? textTheme.titleSmall : textTheme.titleMedium)
                  ?.copyWith(color: accent),
            ),
            if (message != null) ...[
              const SizedBox(height: 6),
              Text(
                message!,
                textAlign: TextAlign.center,
                style: textTheme.bodySmall?.copyWith(
                  color: colorScheme.onSurface.withValues(alpha: 0.55),
                ),
              ),
            ],
            if (onRetry != null) ...[
              SizedBox(height: compact ? 16 : 24),
              _RetryButton(onPressed: onRetry!),
            ],
          ],
        ),
      ),
    );
  }
}

class _RetryButton extends StatelessWidget {
  final VoidCallback onPressed;

  const _RetryButton({required this.onPressed});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Material(
      color: colorScheme.primary,
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          // Clears the 48dp minimum touch target.
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.refresh_rounded,
                size: 18,
                color: colorScheme.onPrimary,
              ),
              const SizedBox(width: 8),
              Text(
                'TRY AGAIN',
                style: Theme.of(context).textTheme.labelLarge?.copyWith(
                  color: colorScheme.onPrimary,
                  letterSpacing: 1.2,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
