import 'package:flutter/material.dart';

import 'pages.dart';
import 'win32.dart';

const koFiUrl = 'https://ko-fi.com/denarmo';
const licenseUrl = 'https://creativecommons.org/licenses/by-nc-sa/4.0/';
const appVersion = '1.1.0';

class SupportPage extends StatelessWidget {
  const SupportPage({super.key});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final t = Theme.of(context).textTheme;
    return PageBody(children: [
      Card.filled(
        color: cs.primaryContainer,
        margin: const EdgeInsets.only(bottom: 16),
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(children: [
            Icon(Icons.favorite, size: 48, color: cs.onPrimaryContainer),
            const SizedBox(height: 12),
            Text('Enjoying the Super Saiyan Mod?', style: t.headlineSmall?.copyWith(color: cs.onPrimaryContainer)),
            const SizedBox(height: 8),
            Text(
              'It\'s free and made in spare time. A tip helps keep it going: new features, '
              'more controllers and firmware versions.',
              textAlign: TextAlign.center,
              style: t.bodyLarge?.copyWith(color: cs.onPrimaryContainer),
            ),
            const SizedBox(height: 20),
            FilledButton.icon(
              style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 18)),
              onPressed: () => openUrl(koFiUrl),
              icon: const Icon(Icons.local_cafe),
              label: const Text('Support on Ko-fi'),
            ),
          ]),
        ),
      ),
      SectionCard(icon: Icons.info_outline, title: 'About', children: [
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Super Saiyan Companion'),
          subtitle: const Text('Version $appVersion · Unofficial community project, not affiliated with GuliKit.'),
        ),
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('License: CC BY-NC-SA 4.0'),
          subtitle: const Text('Free to use, share and fork for non-commercial purposes, with credit and under the '
              'same license. Firmware built with this app contains GuliKit\'s code and must not be shared.'),
          trailing: IconButton(icon: const Icon(Icons.open_in_new), onPressed: () => openUrl(licenseUrl)),
        ),
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: () => showLicensePage(
              context: context,
              applicationName: 'Super Saiyan Companion',
              applicationVersion: appVersion,
            ),
            icon: const Icon(Icons.description_outlined),
            label: const Text('Open-source components'),
          ),
        ),
      ]),
    ]);
  }
}
