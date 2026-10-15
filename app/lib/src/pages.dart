import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'adapter_model.dart';
import 'protocol.dart';

// ---- shared building blocks ----------------------------------------------------

class PageBody extends StatelessWidget {
  const PageBody({super.key, required this.children});
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => ListView(
        padding: const EdgeInsets.fromLTRB(24, 8, 24, 32),
        children: [
          Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 880),
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
            ),
          ),
        ],
      );
}

class SectionCard extends StatelessWidget {
  const SectionCard({super.key, required this.title, this.subtitle, required this.children, this.icon});
  final String title;
  final String? subtitle;
  final IconData? icon;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return Card.filled(
      margin: const EdgeInsets.only(bottom: 16),
      color: cs.surfaceContainerLow,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 18, 20, 12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            if (icon != null) ...[Icon(icon, color: cs.primary), const SizedBox(width: 12)],
            Text(title, style: t.titleMedium),
          ]),
          if (subtitle != null)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(subtitle!, style: t.bodyMedium?.copyWith(color: cs.onSurfaceVariant)),
            ),
          const SizedBox(height: 8),
          ...children,
        ]),
      ),
    );
  }
}

/// Labelled slider that shows its value; edits are sent when the thumb is released.
class SettingSlider extends StatefulWidget {
  const SettingSlider({
    super.key,
    required this.label,
    required this.value,
    required this.min,
    required this.max,
    required this.onChanged,
    this.divisions,
    this.format,
    this.help,
  });
  final String label;
  final String? help;
  final int value, min, max;
  final int? divisions;
  final String Function(int v)? format;
  final ValueChanged<int> onChanged;

  @override
  State<SettingSlider> createState() => _SettingSliderState();
}

class _SettingSliderState extends State<SettingSlider> {
  double? dragging;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    final v = (dragging ?? widget.value.toDouble()).clamp(widget.min.toDouble(), widget.max.toDouble());
    final text = widget.format?.call(v.round()) ?? '${v.round()}';
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Text(widget.label, style: t.bodyLarge)),
          Text(text, style: t.labelLarge?.copyWith(color: cs.primary)),
        ]),
        if (widget.help != null) Text(widget.help!, style: t.bodySmall?.copyWith(color: cs.onSurfaceVariant)),
        Slider(
          value: v,
          min: widget.min.toDouble(),
          max: widget.max.toDouble(),
          divisions: widget.divisions ?? (widget.max - widget.min),
          label: text,
          onChanged: (x) => setState(() => dragging = x),
          onChangeEnd: (x) {
            setState(() => dragging = null);
            widget.onChanged(x.round());
          },
        ),
      ]),
    );
  }
}

class NotConnected extends StatelessWidget {
  const NotConnected({super.key});

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return PageBody(children: [
      SectionCard(
        icon: Icons.usb_off,
        title: 'Looking for your adapter…',
        children: [
          for (final (i, s) in [
            'Plug the Goku 2 adapter into this PC.',
            'Make sure it runs the Super Saiyan firmware: build and install it on the Firmware page.',
            'Put it in Xbox 360 mode: the companion app talks to it through that mode.',
          ].indexed)
            ListTile(
              leading: CircleAvatar(
                radius: 14,
                backgroundColor: cs.primaryContainer,
                child: Text('${i + 1}', style: t.labelLarge?.copyWith(color: cs.onPrimaryContainer)),
              ),
              title: Text(s),
            ),
          Padding(
            padding: const EdgeInsets.all(8),
            child: Text('It connects automatically as soon as it appears.',
                style: t.bodyMedium?.copyWith(color: cs.onSurfaceVariant)),
          ),
        ],
      ),
    ]);
  }
}

// ---- Overview ---------------------------------------------------------------------

class OverviewPage extends StatelessWidget {
  const OverviewPage({super.key, required this.model});
  final AdapterModel model;

  @override
  Widget build(BuildContext context) {
    final i = model.info;
    if (!model.connected || i == null) return const NotConnected();
    final cs = Theme.of(context).colorScheme;
    Widget tile(IconData icon, String title, String value) => Expanded(
          child: Card.filled(
            color: cs.secondaryContainer,
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Icon(icon, color: cs.onSecondaryContainer),
                const SizedBox(height: 12),
                Text(title, style: Theme.of(context).textTheme.labelLarge?.copyWith(color: cs.onSecondaryContainer)),
                Text(value,
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(color: cs.onSecondaryContainer)),
              ]),
            ),
          ),
        );
    return PageBody(children: [
      Row(children: [
        tile(Icons.sports_esports, 'Controller', controllerNames[i.controllerType] ?? 'None connected'),
        tile(Icons.settings_input_hdmi, 'Output mode', outputModeNames[i.outputMode] ?? 'Mode ${i.outputMode}'),
        tile(Icons.memory, 'Mod firmware', 'v${i.firmwareText} (protocol ${i.protocol})'),
      ]),
      const SizedBox(height: 16),
      SectionCard(
        icon: Icons.info_outline,
        title: 'How settings work',
        children: const [
          ListTile(
            leading: Icon(Icons.bolt),
            title: Text('Changes apply instantly'),
            subtitle: Text('Try them with the controller while you adjust.'),
          ),
          ListTile(
            leading: Icon(Icons.save_outlined),
            title: Text('Save keeps them'),
            subtitle: Text('Saved settings live in the adapter and survive unplugging, on any PC or console.'),
          ),
          ListTile(
            leading: Icon(Icons.public),
            title: Text('Features work in every output mode'),
            subtitle: Text('Only configuring needs Xbox 360 mode. The touchpad mouse also needs Xbox 360 mode '
                'and a PS4 or PS5 controller.'),
          ),
        ],
      ),
    ]);
  }
}

// ---- Touchpad ---------------------------------------------------------------------

class TouchpadPage extends StatelessWidget {
  const TouchpadPage({super.key, required this.model});
  final AdapterModel model;

  @override
  Widget build(BuildContext context) {
    final s = model.settings!;
    void u8(Field f, int v) => model.edit(f, (s) => s.setU8(f, v));
    void u16(Field f, int v) => model.edit(f, (s) => s.setU16(f, v));
    final on = s.u8(Settings.tmEnable) != 0;
    return PageBody(children: [
      SectionCard(
        icon: Icons.mouse_outlined,
        title: 'Touchpad as mouse',
        subtitle: 'PS4 / PS5 controllers in Xbox 360 mode: one finger moves the cursor, two fingers '
            'scroll. Tap to left-click, hold to right-click, press and move to drag.',
        children: [
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Enable touchpad mouse'),
            value: on,
            onChanged: (v) => u8(Settings.tmEnable, v ? 1 : 0),
          ),
        ],
      ),
      if (on) ...[
        SectionCard(title: 'Pointer', icon: Icons.near_me_outlined, children: [
          SettingSlider(
            label: 'Cursor speed',
            value: s.u8(Settings.tmSpeed),
            min: 1,
            max: 24,
            format: (v) => '${(v / 8).toStringAsFixed(2)}×',
            onChanged: (v) => u8(Settings.tmSpeed, v),
          ),
          SettingSlider(
            label: 'Scroll speed',
            help: 'Finger travel per wheel step; less travel scrolls faster.',
            value: 130 - s.u8(Settings.tmScrollDiv),
            min: 10,
            max: 120,
            format: (v) => '${130 - v} units / step',
            onChanged: (v) => u8(Settings.tmScrollDiv, 130 - v),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Reverse scrolling'),
            subtitle: const Text('Content follows your fingers ("natural" scrolling).'),
            value: s.bit(Settings.tmFlags, tmfInvertScroll),
            onChanged: (v) => model.edit(Settings.tmFlags, (s) => s.setBit(Settings.tmFlags, tmfInvertScroll, v)),
          ),
        ]),
        SectionCard(title: 'Clicking', icon: Icons.ads_click, children: [
          SettingSlider(
            label: 'Click deadzone',
            help: 'How far a finger moves before the cursor follows after touching, clicking or releasing.',
            value: s.u16(Settings.tmSlop),
            min: 0,
            max: 200,
            divisions: 40,
            format: (v) => '$v units',
            onChanged: (v) => u16(Settings.tmSlop, v),
          ),
          SettingSlider(
            label: 'Drag threshold',
            help: 'While the pad is pressed: movement needed to start a left-drag instead of a right-click.',
            value: s.u16(Settings.tmDragSlop),
            min: 40,
            max: 400,
            divisions: 36,
            format: (v) => '$v units',
            onChanged: (v) => u16(Settings.tmDragSlop, v),
          ),
          SettingSlider(
            label: 'Right-click hold time',
            value: s.u16(Settings.tmHoldMs),
            min: 200,
            max: 1500,
            divisions: 26,
            format: (v) => '$v ms',
            onChanged: (v) => u16(Settings.tmHoldMs, v),
          ),
        ]),
      ],
    ]);
  }
}

// ---- Buttons ----------------------------------------------------------------------

class ButtonsPage extends StatelessWidget {
  const ButtonsPage({super.key, required this.model});
  final AdapterModel model;

  @override
  Widget build(BuildContext context) {
    final s = model.settings!;
    final cs = Theme.of(context).colorScheme;
    Widget maskChips(Field f) => Wrap(spacing: 8, runSpacing: 8, children: [
          for (var i = 0; i < 20; i++)
            FilterChip(
              label: Text(buttonShort[i]),
              tooltip: buttonNames[i],
              selected: s.u32(f) & (1 << i) != 0,
              onSelected: (v) => model.edit(f, (s) => s.setU32(f, v ? s.u32(f) | 1 << i : s.u32(f) & ~(1 << i))),
            ),
        ]);
    return PageBody(children: [
      SectionCard(
        icon: Icons.swap_horiz,
        title: 'Remap',
        subtitle: 'Choose what each physical button sends. Works with every controller and output mode.',
        children: [
          LayoutBuilder(builder: (context, c) {
            final w = (c.maxWidth - 16) / 2;
            return Wrap(spacing: 16, runSpacing: 4, children: [
              for (var i = 0; i < 20; i++)
                SizedBox(
                  width: w,
                  child: Row(children: [
                    Expanded(child: Text(buttonNames[i])),
                    Icon(Icons.arrow_forward, size: 16, color: cs.onSurfaceVariant),
                    const SizedBox(width: 8),
                    DropdownButton<int>(
                      value: s.u8(Settings.remap, i) < 20 ? s.u8(Settings.remap, i) : 255,
                      underline: const SizedBox(),
                      items: [
                        for (var j = 0; j < 20; j++)
                          DropdownMenuItem(
                            value: j,
                            child: Text(buttonShort[j],
                                style: j == i ? null : TextStyle(color: cs.primary, fontWeight: FontWeight.w600)),
                          ),
                        const DropdownMenuItem(value: 255, child: Text('Off')),
                      ],
                      onChanged: (v) => model.edit(Settings.remap, (s) => s.setU8(Settings.remap, v!, i)),
                    ),
                  ]),
                ),
            ]);
          }),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
              onPressed: () => model.edit(Settings.remap, (s) {
                for (var i = 0; i < 20; i++) {
                  s.setU8(Settings.remap, i, i);
                }
              }),
              icon: const Icon(Icons.undo),
              label: const Text('Reset remap'),
            ),
          ),
        ],
      ),
      SectionCard(
        icon: Icons.fast_forward_outlined,
        title: 'Turbo',
        subtitle: 'Held buttons repeat automatically. Applies to the physical button, before remapping.',
        children: [
          maskChips(Settings.turboMask),
          const SizedBox(height: 8),
          SettingSlider(
            label: 'Turbo rate',
            value: s.u8(Settings.turboRate).clamp(2, 30),
            min: 2,
            max: 30,
            format: (v) => '$v presses / s',
            onChanged: (v) => model.edit(Settings.turboRate, (s) => s.setU8(Settings.turboRate, v)),
          ),
        ],
      ),
      SectionCard(
        icon: Icons.toggle_on_outlined,
        title: 'Toggle (latch)',
        subtitle: 'Tap once to hold the button down, tap again to release: e.g. sprint or crouch.',
        children: [maskChips(Settings.toggleMask)],
      ),
    ]);
  }
}

// ---- Sticks -----------------------------------------------------------------------

class SticksPage extends StatelessWidget {
  const SticksPage({super.key, required this.model});
  final AdapterModel model;

  @override
  Widget build(BuildContext context) {
    final s = model.settings!;
    Widget stick(int i, String name, int invX, int invY) => Expanded(
          child: SectionCard(icon: Icons.radio_button_checked, title: name, children: [
            SettingSlider(
              label: 'Deadzone',
              help: 'Small movements around the center are ignored.',
              value: s.u8(Settings.stickDz, i),
              min: 0,
              max: 40,
              format: (v) => '$v %',
              onChanged: (v) => model.edit(Settings.stickDz, (s) => s.setU8(Settings.stickDz, v, i)),
            ),
            SettingSlider(
              label: 'Anti-deadzone',
              help: "Smallest output, to cancel out a game's own deadzone.",
              value: s.u8(Settings.stickAntiDz, i),
              min: 0,
              max: 40,
              format: (v) => '$v %',
              onChanged: (v) => model.edit(Settings.stickAntiDz, (s) => s.setU8(Settings.stickAntiDz, v, i)),
            ),
            SettingSlider(
              label: 'Response curve',
              help: '0 = linear; higher = finer control near the center.',
              value: s.u8(Settings.stickCurve, i),
              min: 0,
              max: 100,
              divisions: 20,
              format: (v) => v == 0 ? 'Linear' : '$v %',
              onChanged: (v) => model.edit(Settings.stickCurve, (s) => s.setU8(Settings.stickCurve, v, i)),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Invert horizontal'),
              value: s.bit(Settings.stickFlags, invX),
              onChanged: (v) => model.edit(Settings.stickFlags, (s) => s.setBit(Settings.stickFlags, invX, v)),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Invert vertical'),
              value: s.bit(Settings.stickFlags, invY),
              onChanged: (v) => model.edit(Settings.stickFlags, (s) => s.setBit(Settings.stickFlags, invY, v)),
            ),
          ]),
        );
    final dpadMode = s.bit(Settings.stickFlags, sfDpadToLstick)
        ? 1
        : s.bit(Settings.stickFlags, sfLstickToDpad)
            ? 2
            : 0;
    return PageBody(children: [
      Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        stick(0, 'Left stick', sfInvLx, sfInvLy),
        const SizedBox(width: 16),
        stick(1, 'Right stick', sfInvRx, sfInvRy),
      ]),
      SectionCard(icon: Icons.swap_calls, title: 'Layout', children: [
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Swap sticks'),
          subtitle: const Text('Southpaw: the left stick acts as the right one and vice versa.'),
          value: s.bit(Settings.stickFlags, sfSwapSticks),
          onChanged: (v) => model.edit(Settings.stickFlags, (s) => s.setBit(Settings.stickFlags, sfSwapSticks, v)),
        ),
        const SizedBox(height: 8),
        const Text('D-pad and left stick'),
        const SizedBox(height: 8),
        SegmentedButton<int>(
          segments: const [
            ButtonSegment(value: 0, label: Text('Normal')),
            ButtonSegment(value: 1, label: Text('D-pad → left stick')),
            ButtonSegment(value: 2, label: Text('Left stick → D-pad')),
          ],
          selected: {dpadMode},
          onSelectionChanged: (v) => model.edit(Settings.stickFlags, (s) {
            s.setBit(Settings.stickFlags, sfDpadToLstick, v.first == 1);
            s.setBit(Settings.stickFlags, sfLstickToDpad, v.first == 2);
          }),
        ),
        const SizedBox(height: 8),
      ]),
    ]);
  }
}

// ---- Triggers & D-pad -----------------------------------------------------------------

class TriggersPage extends StatelessWidget {
  const TriggersPage({super.key, required this.model});
  final AdapterModel model;

  @override
  Widget build(BuildContext context) {
    final s = model.settings!;
    Widget trig(int i, String name, int hair) => Expanded(
          child: SectionCard(icon: Icons.linear_scale, title: name, children: [
            SettingSlider(
              label: 'Deadzone',
              help: 'Light presses below this are ignored.',
              value: s.u8(Settings.trigDz, i),
              min: 0,
              max: 50,
              format: (v) => '$v %',
              onChanged: (v) => model.edit(Settings.trigDz, (s) => s.setU8(Settings.trigDz, v, i)),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Hair trigger'),
              subtitle: const Text('Any press past the deadzone counts as a full press.'),
              value: s.bit(Settings.trigFlags, hair),
              onChanged: (v) => model.edit(Settings.trigFlags, (s) => s.setBit(Settings.trigFlags, hair, v)),
            ),
          ]),
        );
    return PageBody(children: [
      Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        trig(0, 'Left trigger', tfHairL),
        const SizedBox(width: 16),
        trig(1, 'Right trigger', tfHairR),
      ]),
      SectionCard(
        icon: Icons.control_camera,
        title: 'D-pad SOCD cleaning',
        subtitle: 'What happens when opposite directions are pressed together (fighting games).',
        children: [
          SegmentedButton<int>(
            segments: const [
              ButtonSegment(value: 0, label: Text('Off')),
              ButtonSegment(value: 1, label: Text('Neutral')),
              ButtonSegment(value: 2, label: Text('Last input wins')),
              ButtonSegment(value: 3, label: Text('Up priority')),
            ],
            selected: {s.u8(Settings.socd).clamp(0, 3)},
            onSelectionChanged: (v) => model.edit(Settings.socd, (s) => s.setU8(Settings.socd, v.first)),
          ),
          const SizedBox(height: 8),
        ],
      ),
    ]);
  }
}

// ---- Input test -----------------------------------------------------------------------

class InputTestPage extends StatefulWidget {
  const InputTestPage({super.key, required this.model});
  final AdapterModel model;

  @override
  State<InputTestPage> createState() => _InputTestPageState();
}

class _InputTestPageState extends State<InputTestPage> {
  Timer? timer;
  LiveState? live;

  @override
  void initState() {
    super.initState();
    timer = Timer.periodic(const Duration(milliseconds: 33), (_) {
      final l = widget.model.live();
      if (mounted) setState(() => live = l);
    });
  }

  @override
  void dispose() {
    timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l = live;
    final cs = Theme.of(context).colorScheme;
    if (l == null) return const PageBody(children: [LinearProgressIndicator()]);
    final pressed = l.pressed;
    return PageBody(children: [
      SectionCard(
        icon: Icons.sports_esports,
        title: controllerNames[l.type] ?? 'No controller',
        subtitle: 'Raw input from the controller, before remapping and the other features.',
        children: [
          Row(mainAxisAlignment: MainAxisAlignment.spaceEvenly, children: [
            _StickView(label: 'Left stick', x: l.stick(0), y: l.stick(1)),
            Column(children: [
              for (final (i, n) in ['Left trigger', 'Right trigger'].indexed)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: SizedBox(
                    width: 200,
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(n),
                      const SizedBox(height: 6),
                      LinearProgressIndicator(
                          value: l.trigger(i) / 32767, minHeight: 10, borderRadius: BorderRadius.circular(5)),
                    ]),
                  ),
                ),
            ]),
            _StickView(label: 'Right stick', x: l.stick(2), y: l.stick(3)),
          ]),
          const SizedBox(height: 16),
          Wrap(spacing: 8, runSpacing: 8, children: [
            for (var i = 0; i < 20; i++)
              Chip(
                label: Text(buttonShort[i]),
                side: BorderSide.none,
                backgroundColor: pressed.contains(i) ? cs.primary : cs.surfaceContainerHighest,
                labelStyle: TextStyle(color: pressed.contains(i) ? cs.onPrimary : cs.onSurfaceVariant),
              ),
          ]),
        ],
      ),
    ]);
  }
}

class _StickView extends StatelessWidget {
  const _StickView({required this.label, required this.x, required this.y});
  final String label;
  final int x, y;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Column(children: [
      CustomPaint(
        size: const Size(140, 140),
        painter: _StickPainter(x / 32767, y / 32767, cs.outlineVariant, cs.primary),
      ),
      const SizedBox(height: 8),
      Text(label),
      Text('$x, $y', style: Theme.of(context).textTheme.bodySmall),
    ]);
  }
}

class _StickPainter extends CustomPainter {
  _StickPainter(this.x, this.y, this.ring, this.dot);
  final double x, y;
  final Color ring, dot;

  @override
  void paint(Canvas canvas, Size size) {
    final c = size.center(Offset.zero);
    final r = size.width / 2 - 6;
    canvas.drawCircle(c, r, Paint()
      ..color = ring
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2);
    final m = math.sqrt(x * x + y * y);
    final k = m > 1 ? 1 / m : 1.0;
    canvas.drawCircle(c + Offset(x * k * r, -y * k * r), 10, Paint()..color = dot);
  }

  @override
  bool shouldRepaint(_StickPainter o) => o.x != x || o.y != y;
}
