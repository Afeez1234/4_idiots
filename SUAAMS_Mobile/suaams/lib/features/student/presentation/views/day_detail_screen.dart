import 'package:flutter/material.dart';
import '../../../../shared/widgets/coming_soon_screen.dart';

// Placeholder for Timetable > "Day detail (tap a day)".
class DayDetailScreen extends StatelessWidget {
  final String day;

  const DayDetailScreen({super.key, required this.day});

  @override
  Widget build(BuildContext context) {
    return ComingSoonScreen(
      title: day,
      subtitle: 'Full schedule for $day is coming soon.',
      icon: Icons.today_rounded,
    );
  }
}
