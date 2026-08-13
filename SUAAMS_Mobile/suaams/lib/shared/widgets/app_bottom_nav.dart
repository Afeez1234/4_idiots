import 'package:flutter/material.dart';

// Generalized version of the bottom nav bar that used to live as private
// classes (_DashboardBottomNav/_BottomNavItem) inside
// student_dashboard_screen.dart. Now shared between the student and
// lecturer StatefulShellRoute shells so both 5-tab bars look identical.
class AppBottomNavItem {
  final IconData icon;
  final String label;

  const AppBottomNavItem({required this.icon, required this.label});
}

class AppBottomNav extends StatelessWidget {
  final List<AppBottomNavItem> items;
  final int currentIndex;
  final ValueChanged<int> onTap;

  const AppBottomNav({
    super.key,
    required this.items,
    required this.currentIndex,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: BoxDecoration(
          color: colorScheme.surface,
          border: Border(
            top: BorderSide(color: colorScheme.outline.withValues(alpha: 0.15)),
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceAround,
          children: [
            for (var i = 0; i < items.length; i++)
              _AppBottomNavTile(
                item: items[i],
                active: i == currentIndex,
                colorScheme: colorScheme,
                onTap: () => onTap(i),
              ),
          ],
        ),
      ),
    );
  }
}

class _AppBottomNavTile extends StatelessWidget {
  final AppBottomNavItem item;
  final bool active;
  final ColorScheme colorScheme;
  final VoidCallback onTap;

  const _AppBottomNavTile({
    required this.item,
    required this.active,
    required this.colorScheme,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          color: active
              ? colorScheme.primary.withValues(alpha: 0.05)
              : Colors.transparent,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              item.icon,
              size: 20,
              color: active
                  ? colorScheme.primary
                  : colorScheme.onSurface.withValues(alpha: 0.45),
            ),
            const SizedBox(height: 4),
            Text(
              item.label,
              style: TextStyle(
                fontSize: 8,
                fontWeight: FontWeight.bold,
                color: active
                    ? colorScheme.primary
                    : colorScheme.onSurface.withValues(alpha: 0.45),
                letterSpacing: 1,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
