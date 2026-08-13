import 'package:flutter/material.dart';
import '../../../../shared/widgets/coming_soon_screen.dart';

// Reports tab root -- "Course reports list".
class ReportsListScreen extends StatelessWidget {
  const ReportsListScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const ComingSoonScreen(
      title: 'Reports',
      subtitle: 'Course attendance reports are coming soon.',
      icon: Icons.summarize_rounded,
    );
  }
}
