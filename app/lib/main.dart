import 'dart:io';

import 'package:flutter/material.dart';

import 'src/adapter_model.dart';
import 'src/firmware_page.dart';
import 'src/pages.dart';
import 'src/screenshots.dart';
import 'src/support_page.dart';

void main() {
  final shots = Platform.environment['SS_SCREENSHOT_DIR'];
  if (shots != null) {
    runScreenshots(shots);
    return;
  }
  runApp(const CompanionApp());
}

class CompanionApp extends StatefulWidget {
  const CompanionApp({super.key, this.demo, this.page = 0, this.dark});
  final AdapterModel? demo;
  final int page;
  final bool? dark;

  @override
  State<CompanionApp> createState() => _CompanionAppState();
}

class _CompanionAppState extends State<CompanionApp> {
  late final model = widget.demo ?? AdapterModel();

  @override
  void dispose() {
    if (widget.demo == null) model.dispose();
    super.dispose();
  }

  // Brand accent #F1C40F. Yellow is too light for text on white, so the light theme uses a
  // deep gold for text/icons and keeps the bright yellow for filled surfaces (dark text on it).
  static const brand = Color(0xFFF1C40F);

  ThemeData _theme(Brightness b) {
    final dark = b == Brightness.dark;
    final base = ColorScheme.fromSeed(seedColor: brand, brightness: b, dynamicSchemeVariant: DynamicSchemeVariant.fidelity);
    final cs = dark
        ? base.copyWith(
            primary: brand,
            onPrimary: const Color(0xFF1A1400),
            primaryContainer: const Color(0xFF3D3200),
            onPrimaryContainer: const Color(0xFFFFE27A),
            secondaryContainer: const Color(0xFF2E2A1C),
            onSecondaryContainer: const Color(0xFFF0E3B8),
            surface: const Color(0xFF0E0E0F),
            onSurface: const Color(0xFFE8E6E1),
            surfaceContainerLowest: const Color(0xFF080809),
            surfaceContainerLow: const Color(0xFF141415),
            surfaceContainer: const Color(0xFF18181A),
            surfaceContainerHigh: const Color(0xFF202022),
            surfaceContainerHighest: const Color(0xFF2A2A2C),
          )
        : base.copyWith(
            primary: const Color(0xFF7A5F00),
            onPrimary: Colors.white,
            primaryContainer: brand,
            onPrimaryContainer: const Color(0xFF1F1800),
            secondaryContainer: const Color(0xFFFFEFB0),
            onSecondaryContainer: const Color(0xFF2B2300),
            surface: const Color(0xFFFBFAF7),
            onSurface: const Color(0xFF1C1B17),
            surfaceContainerLowest: Colors.white,
            surfaceContainerLow: const Color(0xFFF6F4EE),
            surfaceContainer: const Color(0xFFF1EEE6),
            surfaceContainerHigh: const Color(0xFFEBE8DF),
            surfaceContainerHighest: const Color(0xFFE5E1D7),
          );
    return ThemeData(
      colorScheme: cs,
      scaffoldBackgroundColor: cs.surface,
      useMaterial3: true,
      visualDensity: VisualDensity.standard,
    );
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Super Saiyan Companion',
        debugShowCheckedModeBanner: false,
        theme: _theme(Brightness.light),
        darkTheme: _theme(Brightness.dark),
        themeMode: widget.dark == null ? ThemeMode.system : (widget.dark! ? ThemeMode.dark : ThemeMode.light),
        home: ListenableBuilder(
            listenable: model, builder: (context, _) => HomePage(model: model, initialPage: widget.page)),
      );
}

class HomePage extends StatefulWidget {
  const HomePage({super.key, required this.model, this.initialPage = 0});
  final AdapterModel model;
  final int initialPage;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  late int index = widget.initialPage;

  static const destinations = [
    (Icons.dashboard_outlined, Icons.dashboard, 'Overview'),
    (Icons.system_update_alt_outlined, Icons.system_update_alt, 'Firmware'),
    (Icons.touch_app_outlined, Icons.touch_app, 'Touchpad'),
    (Icons.gamepad_outlined, Icons.gamepad, 'Buttons'),
    (Icons.radio_button_checked_outlined, Icons.radio_button_checked, 'Sticks'),
    (Icons.linear_scale_outlined, Icons.linear_scale, 'Triggers & D-pad'),
    (Icons.monitor_heart_outlined, Icons.monitor_heart, 'Input test'),
    (Icons.favorite_outline, Icons.favorite, 'Support'),
  ];

  @override
  Widget build(BuildContext context) {
    final m = widget.model;
    final needsAdapter = index >= 2 && index <= 6;
    final page = !m.connected && needsAdapter
        ? const NotConnected()
        : switch (index) {
            0 => OverviewPage(model: m),
            1 => const FirmwarePage(),
            2 => TouchpadPage(model: m),
            3 => ButtonsPage(model: m),
            4 => SticksPage(model: m),
            5 => TriggersPage(model: m),
            6 => InputTestPage(model: m),
            _ => const SupportPage(),
          };
    return Scaffold(
      body: Row(children: [
        NavigationRail(
          selectedIndex: index,
          onDestinationSelected: (i) => setState(() => index = i),
          labelType: NavigationRailLabelType.all,
          leading: Padding(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: Image.asset('assets/app_icon.png', width: 44, height: 44, filterQuality: FilterQuality.medium),
          ),
          destinations: [
            for (final (icon, selected, label) in destinations)
              NavigationRailDestination(icon: Icon(icon), selectedIcon: Icon(selected), label: Text(label)),
          ],
        ),
        Expanded(
          child: Column(children: [
            _TopBar(model: m, title: destinations[index].$3),
            Expanded(child: page),
          ]),
        ),
      ]),
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({required this.model, required this.title});
  final AdapterModel model;
  final String title;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final t = Theme.of(context).textTheme;
    final m = model;
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 20, 24, 8),
      child: Row(children: [
        Text(title, style: t.headlineSmall),
        const SizedBox(width: 16),
        Chip(
          avatar: Icon(m.connected ? Icons.usb : Icons.usb_off,
              size: 18, color: m.connected ? cs.primary : cs.error),
          label: Text(m.connected ? 'Adapter connected' : 'Not connected'),
          side: BorderSide.none,
          backgroundColor: m.connected ? cs.secondaryContainer : cs.errorContainer,
        ),
        const Spacer(),
        if (m.connected) ...[
          if (m.dirty)
            Padding(
              padding: const EdgeInsets.only(right: 12),
              child: Text('Unsaved changes', style: t.labelLarge?.copyWith(color: cs.tertiary)),
            ),
          OutlinedButton.icon(
            onPressed: () => _confirmDefaults(context),
            icon: const Icon(Icons.restart_alt),
            label: const Text('Defaults'),
          ),
          const SizedBox(width: 8),
          FilledButton.icon(
            onPressed: m.dirty
                ? () async {
                    final ok = await m.save();
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                        content: Text(ok ? 'Saved to the adapter' : 'Saving failed: ${m.lastError}'),
                      ));
                    }
                  }
                : null,
            icon: const Icon(Icons.save_outlined),
            label: const Text('Save to adapter'),
          ),
        ],
      ]),
    );
  }

  Future<void> _confirmDefaults(BuildContext context) async {
    final yes = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        icon: const Icon(Icons.restart_alt),
        title: const Text('Restore defaults?'),
        content: const Text('Every setting goes back to its default right away. '
            'Nothing is stored until you press Save.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Restore')),
        ],
      ),
    );
    if (yes == true) model.defaults();
  }
}
