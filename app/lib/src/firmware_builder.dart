// Builds the Super Saiyan firmware from the user's own official GuliKit file.
// The app only ships our patch (assets/firmware_patch.json, made by tools/make_patch.py):
// our code plus copy instructions. No GuliKit code is included or distributed.
import 'dart:convert';
import 'dart:io';

import 'package:archive/archive.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';

const _updateMagic = 'GULIKIT_NS36_UPDATE_BIN';

class FirmwarePatch {
  FirmwarePatch._(this.json);
  final Map<String, dynamic> json;

  static Future<FirmwarePatch> load() async =>
      FirmwarePatch._(jsonDecode(await rootBundle.loadString('assets/firmware_patch.json')) as Map<String, dynamic>);

  String get version => json['version'] as String;
  String get baseName => (json['base'] as Map)['name'] as String;
  int get baseSize => (json['base'] as Map)['size'] as int;
  String get baseSha => (json['base'] as Map)['sha256'] as String;
  String get resultSha => json['result_sha256'] as String;
  String get outputName => 'GokuSuperSaiyan_$version.bin';

  Uint8List apply(Uint8List base) {
    final out = Uint8List.fromList(base);
    for (final op in (json['ops'] as List).cast<Map<String, dynamic>>()) {
      final at = op['at'] as int;
      final w = op['write'] as String?;
      if (w != null) {
        for (var i = 0; i < w.length; i += 2) {
          out[at + i ~/ 2] = int.parse(w.substring(i, i + 2), radix: 16);
        }
      } else {
        final src = op['copy_from'] as int, n = op['len'] as int;
        out.setRange(at, at + n, base, src);
      }
    }
    return out;
  }
}

class FirmwareException implements Exception {
  FirmwareException(this.message);
  final String message;
  @override
  String toString() => message;
}

String sha256Hex(List<int> data) => sha256.convert(data).toString();

/// Checks [bytes] against the supported official firmware; explains what's wrong otherwise.
void checkOfficial(FirmwarePatch p, Uint8List bytes) {
  final h = sha256Hex(bytes);
  if (h == p.baseSha) return;
  if (h == p.resultSha) {
    throw FirmwareException('This file is already a Super Saiyan build. Choose the official GuliKit file.');
  }
  final head = bytes.length >= _updateMagic.length ? ascii.decode(bytes.sublist(0, _updateMagic.length), allowInvalid: true) : '';
  if (head == _updateMagic) {
    throw FirmwareException('This is Goku 2 firmware, but not version 3.4. Only the official V3.4 file is '
        'supported for now.');
  }
  throw FirmwareException("This isn't a Goku 2 (NS36) firmware file.");
}

/// Reads the official firmware from a .bin, or from the .bin inside an official .zip.
Uint8List readFirmwareFile(FirmwarePatch p, String path) {
  final data = File(path).readAsBytesSync();
  if (!path.toLowerCase().endsWith('.zip')) return data;
  final zip = ZipDecoder().decodeBytes(data);
  for (final f in zip.files) {
    if (f.isFile && f.name.toLowerCase().endsWith('.bin')) {
      final b = Uint8List.fromList(f.content as List<int>);
      if (b.length == p.baseSize && sha256Hex(b) == p.baseSha) return b;
    }
  }
  final bins = zip.files.where((f) => f.isFile && f.name.toLowerCase().endsWith('.bin')).toList();
  if (bins.isEmpty) throw FirmwareException('No .bin firmware file inside this zip.');
  return Uint8List.fromList(bins.first.content as List<int>); // checkOfficial explains the mismatch
}

/// Official file -> Super Saiyan firmware, verified against the expected result.
Uint8List buildFirmware(FirmwarePatch p, Uint8List official) {
  checkOfficial(p, official);
  final out = p.apply(official);
  if (sha256Hex(out) != p.resultSha) {
    throw FirmwareException('Internal check failed: the built image is not the expected one.');
  }
  return out;
}
