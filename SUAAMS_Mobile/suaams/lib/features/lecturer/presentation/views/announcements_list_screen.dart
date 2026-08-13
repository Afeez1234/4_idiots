import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

// Announce tab root -- "Announcements list". No announcements provider/
// endpoint exists yet, so this shows an empty state with the entry point
// into "Create announcement" wired up (the one part of this tab that's
// genuinely actionable today).
class AnnouncementsListScreen extends StatelessWidget {
  const AnnouncementsListScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: const Text('Announcements'),
        backgroundColor: colorScheme.surface,
        elevation: 0,
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.campaign_rounded,
                size: 48,
                color: colorScheme.onSurface.withValues(alpha: 0.2),
              ),
              const SizedBox(height: 16),
              Text(
                'NO ANNOUNCEMENTS YET',
                style: TextStyle(
                  fontFamily: 'JetBrains Mono',
                  fontSize: 12,
                  fontWeight: FontWeight.bold,
                  color: colorScheme.onSurface.withValues(alpha: 0.5),
                ),
              ),
            ],
          ),
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => context.push('/lecturer/announce/create'),
        icon: const Icon(Icons.add_rounded),
        label: const Text('NEW'),
      ),
    );
  }
}
