// Applies the shipped patch to a local copy of the official firmware (never committed;
// put it at ../firmware/NS36_V3.4.bin) and checks the result. Skipped without the file.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:super_saiyan_companion/src/firmware_builder.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final official = File('../firmware/NS36_V3.4.bin');

  test('patch builds the expected firmware from the official file', () async {
    final p = await FirmwarePatch.load();
    final out = buildFirmware(p, Uint8List.fromList(official.readAsBytesSync()));
    expect(sha256Hex(out), p.resultSha);
    expect(() => checkOfficial(p, out), throwsA(isA<FirmwareException>()));
  }, skip: !official.existsSync());

  final zip = File('../NS36_V3.4.zip');
  test('reads the firmware from the official zip', () async {
    final p = await FirmwarePatch.load();
    expect(sha256Hex(readFirmwareFile(p, zip.path)), p.baseSha);
  }, skip: !zip.existsSync());

  test('rejects files that are not the official firmware', () async {
    final p = await FirmwarePatch.load();
    expect(() => checkOfficial(p, Uint8List.fromList(utf8.encode('hello'))), throwsA(isA<FirmwareException>()));
  });
}
