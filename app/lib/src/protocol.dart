// The adapter's config protocol (HID feature report 2) and the settings layout.
// Keep in sync with mods/super_saiyan/ss.h and config.c.
import 'dart:typed_data';

import 'hid_windows.dart';

const adapterVid = 0x1209, adapterPid = 0x0001, configUsagePage = 0xFF00;

enum Cmd { none, info, read, write, save, defaults, live }

/// Logical buttons (LB_* in the firmware SDK), in firmware order.
const buttonNames = [
  'South (A / Cross)', 'East (B / Circle)', 'West (X / Square)', 'North (Y / Triangle)',
  'L (LB / L1)', 'R (RB / R1)', 'Select (Back / Share)', 'Start (Menu / Options)',
  'Left stick click', 'Right stick click', 'D-pad up', 'D-pad down', 'D-pad left', 'D-pad right',
  'Home (Guide / PS)', 'Capture / Touchpad click', 'Paddle 1', 'Paddle 2', 'Paddle 3', 'Paddle 4',
];
const buttonShort = [
  'A', 'B', 'X', 'Y', 'LB', 'RB', 'Back', 'Start', 'LS', 'RS',
  'Up', 'Down', 'Left', 'Right', 'Home', 'Capture', 'P1', 'P2', 'P3', 'P4',
];

/// Firmware table 0x1001C228: controller type -> native bit of each logical button (255 = none).
const nativeBits = [
  [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  [2, 3, 0, 1, 22, 6, 8, 9, 11, 10, 17, 16, 19, 18, 12, 13, 255, 255, 255, 255],
  [2, 3, 0, 1, 22, 6, 8, 9, 11, 10, 17, 16, 19, 18, 12, 13, 255, 255, 255, 255],
  [2, 3, 0, 1, 22, 6, 8, 9, 11, 10, 17, 16, 19, 18, 12, 13, 255, 255, 255, 255],
  [0, 1, 3, 4, 6, 7, 10, 11, 13, 14, 20, 21, 22, 23, 17, 255, 255, 255, 255, 255],
  [5, 6, 4, 7, 8, 9, 12, 13, 14, 15, 0, 2, 3, 1, 16, 17, 255, 255, 255, 255],
  [5, 6, 4, 7, 8, 9, 12, 13, 14, 15, 0, 2, 3, 1, 16, 17, 20, 21, 22, 23],
  [5, 6, 4, 7, 8, 9, 12, 13, 14, 15, 0, 2, 3, 1, 16, 17, 20, 21, 22, 23],
];

const controllerNames = {
  1: 'Nintendo controller', 2: 'Nintendo controller', 3: 'Nintendo controller',
  4: 'Xbox Wireless Controller', 5: 'DualShock 4', 6: 'DualSense', 7: 'DualSense Edge',
};
const outputModeNames = {
  0: 'Detecting…', 1: 'Switch Pro', 2: 'Xbox 360', 3: 'Xbox One', 4: 'PS4', 5: 'PS5', 6: 'Switch 2',
};

/// A field of the settings struct.
class Field {
  const Field(this.offset, this.size);
  final int offset, size;
}

/// The packed settings struct (ss_settings_t), edited in place.
class Settings {
  Settings(this.bytes);
  final Uint8List bytes;
  ByteData get _d => bytes.buffer.asByteData();

  static const tmEnable = Field(2, 1), tmSpeed = Field(3, 1), tmScrollDiv = Field(4, 1), tmFlags = Field(5, 1);
  static const tmSlop = Field(6, 2), tmDragSlop = Field(8, 2), tmHoldMs = Field(10, 2);
  static const remap = Field(12, 20), turboMask = Field(32, 4), turboRate = Field(36, 1);
  static const toggleMask = Field(37, 4), socd = Field(41, 1);
  static const stickDz = Field(42, 2), stickAntiDz = Field(44, 2), stickCurve = Field(46, 2);
  static const stickFlags = Field(48, 1), trigDz = Field(49, 2), trigFlags = Field(51, 1);

  int u8(Field f, [int i = 0]) => bytes[f.offset + i];
  void setU8(Field f, int v, [int i = 0]) => bytes[f.offset + i] = v;
  int u16(Field f) => _d.getUint16(f.offset, Endian.little);
  void setU16(Field f, int v) => _d.setUint16(f.offset, v, Endian.little);
  int u32(Field f) => _d.getUint32(f.offset, Endian.little);
  void setU32(Field f, int v) => _d.setUint32(f.offset, v, Endian.little);
  bool bit(Field f, int mask) => u8(f) & mask != 0;
  void setBit(Field f, int mask, bool on) => setU8(f, on ? u8(f) | mask : u8(f) & ~mask);
}

// stick_flags / trig_flags / tm_flags bits
const sfInvLx = 0x01, sfInvLy = 0x02, sfInvRx = 0x04, sfInvRy = 0x08, sfSwapSticks = 0x10;
const sfDpadToLstick = 0x20, sfLstickToDpad = 0x40, tfHairL = 0x01, tfHairR = 0x02, tmfInvertScroll = 0x01;

class AdapterInfo {
  AdapterInfo(Uint8List r)
      : protocol = r[3],
        firmware = r[4] | r[5] << 8,
        settingsSize = r[6],
        outputMode = r[7],
        controllerType = r[8];
  final int protocol, firmware, settingsSize, outputMode, controllerType;
  String get firmwareText => '${firmware >> 8}.${(firmware & 0xFF).toRadixString(16).padLeft(2, '0')}';
}

class LiveState {
  LiveState(Uint8List r) : _d = ByteData.sublistView(r, 3);
  final ByteData _d;
  int get type => _d.getUint32(0, Endian.little);
  int get nativeButtons => _d.getUint32(8, Endian.little);
  int stick(int i) => _d.getInt16(0x0C + 2 * i, Endian.little); // lx, ly, rx, ry
  int trigger(int i) => _d.getUint16(0x14 + 2 * i, Endian.little);

  /// Logical buttons pressed, via the firmware's per-controller table.
  Set<int> get pressed {
    final t = type < nativeBits.length ? type : 0;
    return {
      for (var i = 0; i < 20; i++)
        if (t != 0 && nativeBits[t][i] != 255 && nativeButtons & (1 << nativeBits[t][i]) != 0) i
    };
  }
}

class ProtocolException implements Exception {
  ProtocolException(this.message);
  final String message;
  @override
  String toString() => message;
}

/// Talks to the adapter over its vendor HID collection.
class AdapterClient {
  AdapterClient._(this._dev);
  final HidDevice _dev;

  static AdapterClient? connect() {
    final d = HidDevice.open(adapterVid, adapterPid, configUsagePage);
    return d == null ? null : AdapterClient._(d);
  }

  Uint8List _cmd(Cmd c, [int a0 = 0, int a1 = 0, List<int> data = const []]) {
    final out = Uint8List(64)
      ..[0] = 2
      ..[1] = c.index
      ..[2] = a0
      ..[3] = a1
      ..setAll(4, data);
    if (!_dev.setFeature(out)) throw ProtocolException('Adapter disconnected');
    final r = _dev.getFeature(2, 64);
    if (r == null) throw ProtocolException('Adapter disconnected');
    if (r[1] != c.index || r[2] != 0) throw ProtocolException('Adapter rejected command ${c.name}');
    return r;
  }

  AdapterInfo info() => AdapterInfo(_cmd(Cmd.info));

  Settings readSettings(int size) {
    final b = BytesBuilder();
    while (b.length < size) {
      final n = (size - b.length).clamp(0, 58);
      b.add(_cmd(Cmd.read, b.length, n).sublist(5, 5 + n));
    }
    return Settings(b.toBytes());
  }

  void write(Settings s, Field f) => _cmd(Cmd.write, f.offset, f.size, s.bytes.sublist(f.offset, f.offset + f.size));
  void save() => _cmd(Cmd.save);
  void defaults() => _cmd(Cmd.defaults);
  LiveState live() => LiveState(_cmd(Cmd.live));
  void close() => _dev.close();
}
