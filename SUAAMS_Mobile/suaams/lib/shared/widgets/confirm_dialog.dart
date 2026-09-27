import 'package:flutter/material.dart';

/// Shared "are you sure" prompt for destructive or irreversible actions.
///
/// Returns true only when the user taps the confirm button; false on the
/// cancel button, on a barrier/outside tap, or on back navigation. The
/// caller must therefore treat `false` as "nothing happened" rather than
/// checking for a null result -- there is no third case to handle.
///
/// The dialog always pops itself and hands the decision back through the
/// return value. It never performs the action itself: [Navigator.pop] from
/// inside a dialog builder tears down the dialog's own route, and
/// `ref.invalidate` / a provider call made at that point would race the
/// pop animation. Existing callers (`_endSession` in
/// course_workspace_screen.dart, `_confirmDelete` in
/// announcements_list_screen.dart) already follow this shape -- this
/// helper just centralises the styling they duplicate.
///
/// Styling matches the hand-rolled sign-out dialogs: `surfaceContainer`
/// background so it sits above the midnight-black theme, and a CANCEL
/// action in `onSurface` so the destructive button carries the emphasis.
Future<bool> showConfirmDialog(
  BuildContext context, {
  required String title,
  required String message,
  String confirmLabel = 'CONFIRM',
  bool destructive = false,
}) async {
  final colorScheme = Theme.of(context).colorScheme;

  final confirmed = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      backgroundColor: colorScheme.surfaceContainer,
      title: Text(
        title,
        style: const TextStyle(fontWeight: FontWeight.bold),
      ),
      content: Text(message),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context, false),
          child: Text(
            'CANCEL',
            style: TextStyle(color: colorScheme.onSurface),
          ),
        ),
        ElevatedButton(
          // Destructive actions get the error colour so the button itself
          // signals which choice is the risky one; non-destructive
          // confirms keep the default primary styling.
          style: destructive
              ? ElevatedButton.styleFrom(
                  backgroundColor: colorScheme.error,
                  foregroundColor: colorScheme.onError,
                )
              : null,
          onPressed: () => Navigator.pop(context, true),
          child: Text(confirmLabel),
        ),
      ],
    ),
  );

  // showDialog returns null if the route is dismissed without a result
  // (barrier tap, back button, or a popped navigator). Collapse that to
  // false so callers can use a plain `if (confirmed)`.
  return confirmed ?? false;
}
