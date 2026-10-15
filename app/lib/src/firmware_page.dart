import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'firmware_builder.dart';
import 'pages.dart';
import 'win32.dart';

/// Where users get the official firmware (set to GuliKit's support/download page).
const officialFirmwarePage = 'https://www.gulikit.com/newsinfo/3196031.html';

class FirmwarePage extends StatefulWidget {
  const FirmwarePage({super.key});

  @override
  State<FirmwarePage> createState() => _FirmwarePageState();
}

class _FirmwarePageState extends State<FirmwarePage> {
  FirmwarePatch? patch;
  String? officialPath, error, status;
  Uint8List? official, built;
  String? drive;
  Timer? driveTimer;

  @override
  void initState() {
    super.initState();
    FirmwarePatch.load().then((p) => setState(() => patch = p));
    driveTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      final d = findUpdateDrive();
      if (d != drive && mounted) setState(() => drive = d);
    });
  }

  @override
  void dispose() {
    driveTimer?.cancel();
    super.dispose();
  }

  void _choose() {
    final p = patch;
    final path = pickFirmwareFile();
    if (p == null || path == null) return;
    setState(() {
      officialPath = path;
      official = built = null;
      error = status = null;
      try {
        final b = readFirmwareFile(p, path);
        checkOfficial(p, b);
        official = b;
      } on FirmwareException catch (e) {
        error = e.message;
      } on Exception catch (e) {
        error = 'Could not read the file: $e';
      }
    });
  }

  void _build() {
    setState(() {
      try {
        built = buildFirmware(patch!, official!);
        status = null;
      } on FirmwareException catch (e) {
        error = e.message;
      }
    });
  }

  void _save() {
    final path = pickSaveLocation(patch!.outputName);
    if (path == null) return;
    File(path).writeAsBytesSync(built!);
    setState(() => status = 'Saved to $path');
  }

  Future<void> _install(Uint8List image, String name, String what) async {
    final d = drive;
    if (d == null) return;
    try {
      File('$d$name').writeAsBytesSync(image, flush: true);
      setState(() => status = '$what copied to the adapter. Unplug it and plug it back in to finish.');
    } on FileSystemException catch (e) {
      setState(() => error = 'Copying to the adapter failed: ${e.message}');
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = patch;
    final cs = Theme.of(context).colorScheme;
    final t = Theme.of(context).textTheme;
    if (p == null) return const PageBody(children: [LinearProgressIndicator()]);
    Widget step(int n, String title, String body, List<Widget> actions, {bool done = false, bool enabled = true}) =>
        Opacity(
          opacity: enabled ? 1 : 0.5,
          child: SectionCard(
            title: title,
            icon: done ? Icons.check_circle : [Icons.looks_one, Icons.looks_two, Icons.looks_3][n - 1],
            subtitle: body,
            children: [
              Wrap(spacing: 8, runSpacing: 8, children: actions),
              const SizedBox(height: 8),
            ],
          ),
        );
    return PageBody(children: [
      Card.filled(
        color: cs.primaryContainer,
        margin: const EdgeInsets.only(bottom: 16),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Row(children: [
            Icon(Icons.bolt, size: 40, color: cs.onPrimaryContainer),
            const SizedBox(width: 16),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('Super Saiyan firmware ${p.version}',
                    style: t.titleLarge?.copyWith(color: cs.onPrimaryContainer)),
                Text('Built on this PC from your own copy of the official firmware (${p.baseName}). '
                    'This app contains no GuliKit code.',
                    style: t.bodyMedium?.copyWith(color: cs.onPrimaryContainer)),
              ]),
            ),
          ]),
        ),
      ),
      step(
        1,
        'Get the official firmware',
        "Download GuliKit's firmware V3.4 for the Goku 2 adapter (the .zip or the .bin inside it).",
        [
          OutlinedButton.icon(
            onPressed: () => openUrl(officialFirmwarePage),
            icon: const Icon(Icons.open_in_new),
            label: const Text('Open GuliKit website'),
          ),
        ],
        done: official != null,
      ),
      step(
        2,
        'Choose the file',
        official != null
            ? 'Verified: official ${p.baseName}.\n$officialPath'
            : 'The app checks that it is exactly the official file before using it.',
        [
          FilledButton.tonalIcon(onPressed: _choose, icon: const Icon(Icons.folder_open), label: const Text('Choose file…')),
        ],
        done: official != null,
      ),
      step(
        3,
        'Build and install',
        drive != null
            ? 'Adapter found in update mode ($drive).'
            : 'To install directly: hold the side button of the adapter while you plug it in. It appears as a '
                '"GuliKit" drive.',
        [
          FilledButton.icon(
            onPressed: official != null && built == null ? _build : null,
            icon: const Icon(Icons.construction),
            label: const Text('Build firmware'),
          ),
          FilledButton.icon(
            onPressed: built != null && drive != null ? () => _install(built!, p.outputName, 'Super Saiyan firmware') : null,
            icon: const Icon(Icons.system_update_alt),
            label: const Text('Install on adapter'),
          ),
          OutlinedButton.icon(
            onPressed: built != null ? _save : null,
            icon: const Icon(Icons.save_alt),
            label: const Text('Save as…'),
          ),
          TextButton.icon(
            onPressed: official != null && drive != null
                ? () => _install(official!, 'NS36_V3.4.bin', 'Official firmware')
                : null,
            icon: const Icon(Icons.settings_backup_restore),
            label: const Text('Restore official firmware'),
          ),
        ],
        done: built != null,
        enabled: official != null,
      ),
      if (error != null)
        Card.filled(
          color: cs.errorContainer,
          child: ListTile(
            leading: Icon(Icons.error_outline, color: cs.onErrorContainer),
            title: Text(error!, style: TextStyle(color: cs.onErrorContainer)),
          ),
        ),
      if (status != null)
        Card.filled(
          color: cs.tertiaryContainer,
          child: ListTile(
            leading: Icon(Icons.info_outline, color: cs.onTertiaryContainer),
            title: Text(status!, style: TextStyle(color: cs.onTertiaryContainer)),
          ),
        ),
      const SizedBox(height: 8),
      Text(
        'Built firmware contains GuliKit\'s code: keep it for your own adapter and don\'t share the file. '
        'Flashing modified firmware is at your own risk; "Restore official firmware" puts the original back.',
        style: t.bodySmall?.copyWith(color: cs.onSurfaceVariant),
      ),
    ]);
  }
}
