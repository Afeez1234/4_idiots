/// Human-readable date labels, without pulling in `intl`.
///
/// The app needed exactly one format -- "Monday, 28 September 2026" -- and
/// `intl` is not currently a direct dependency. Adding a package plus its
/// locale data for a fixed twelve-word lookup is not worth it; if date
/// formatting ever grows past this (relative times, week ranges, term
/// boundaries), reach for `intl` then rather than growing this by hand.
library;

const _weekdays = <String>[
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
];

const _months = <String>[
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

/// "Monday, 28 September 2026".
///
/// This exists because the dashboard says "TODAY'S PROTOCOL" with nothing
/// on screen saying what today is. An app left open since yesterday looks
/// identical to one that's current, which matters on a screen that silently
/// polls a schedule in the background and gives no staleness signal.
String formatDateLabel(DateTime date) {
  // DateTime.weekday is 1=Monday..7=Sunday, matching the list order above.
  final weekday = _weekdays[date.weekday - 1];
  final month = _months[date.month - 1];
  return '$weekday, ${date.day} $month ${date.year}';
}

/// The date [formatDateLabel] would produce for right now. Split out so
/// tests and the various call sites share one definition of "today".
String todayLabel() => formatDateLabel(DateTime.now());
