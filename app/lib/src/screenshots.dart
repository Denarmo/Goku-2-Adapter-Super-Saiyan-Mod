// SS_SCREENSHOT_DIR=<dir> super_saiyan_companion.exe renders every page with demo
// data into <dir>/<page>.png (used for the README), then exits.
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';

import '../main.dart';
import 'adapter_model.dart';
import 'protocol.dart';

const pages = ['overview', 'firmware', 'touchpad', 'buttons', 'sticks', 'triggers', 'input_test', 'support'];

AdapterModel demoModel() {
  final info = Uint8List(64)..setAll(0, [2, 1, 0, 2, 0x10, 0x01, 52, 2, 6, 1, 0x00, 0x17, 0, 0]);
  final s = Settings(Uint8List.fromList([
    1, 52, 1, 6, 40, 1, 48, 0, 160, 0, 0xF4, 1, // touchpad: on, 0.75x, reverse scrolling
    1, 0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, // A <-> B
    0x04, 0, 0, 0, 15, // turbo on X, 15/s
    0x00, 0x01, 0, 0, // toggle: left stick click
    1, // SOCD neutral
    8, 6, 0, 4, 30, 0, 0x02, // sticks
    5, 5, 0x02, // triggers: 5 % deadzone, hair right
  ]));
  final live = Uint8List(64);
  final d = ByteData.sublistView(live, 3);
  d.setUint32(0, 6, Endian.little);
  d.setUint32(8, 1 << 5 | 1 << 9 | 1 << 1, Endian.little); // Cross, R1, D-pad down
  for (final (i, v) in [12000, 21000, -9000, -3000].indexed) {
    d.setInt16(0x0C + 2 * i, v, Endian.little);
  }
  d.setUint16(0x16, 24000, Endian.little);
  return AdapterModel.demo(AdapterInfo(info), s, LiveState(live));
}

Future<void> runScreenshots(String dir) async {
  WidgetsFlutterBinding.ensureInitialized();
  Directory(dir).createSync(recursive: true);
  final model = demoModel();
  for (final dark in [true]) {
    for (final (i, name) in pages.indexed) {
      final key = GlobalKey();
      runApp(RepaintBoundary(key: key, child: CompanionApp(key: UniqueKey(), demo: model, page: i, dark: dark)));
      await Future.delayed(const Duration(milliseconds: 900));
      final boundary = key.currentContext!.findRenderObject() as RenderRepaintBoundary;
      final image = await boundary.toImage(pixelRatio: 1.0);
      final png = await image.toByteData(format: ui.ImageByteFormat.png);
      File('$dir/${name}_${dark ? 'dark' : 'light'}.png').writeAsBytesSync(png!.buffer.asUint8List());
    }
  }
  exit(0);
}
