// Minimal Windows HID access (setupapi + hid.dll) through dart:ffi: find the adapter's
// vendor collection and exchange 64-byte feature reports with it. No plugins needed.
import 'dart:ffi';
import 'dart:typed_data';

import 'package:ffi/ffi.dart';

final _setup = DynamicLibrary.open('setupapi.dll');
final _hid = DynamicLibrary.open('hid.dll');
final _k32 = DynamicLibrary.open('kernel32.dll');

final _hidGuid = _hid.lookupFunction<Void Function(Pointer<Uint8>), void Function(Pointer<Uint8>)>('HidD_GetHidGuid');
final _getClassDevs = _setup.lookupFunction<IntPtr Function(Pointer<Uint8>, Pointer, IntPtr, Uint32),
    int Function(Pointer<Uint8>, Pointer, int, int)>('SetupDiGetClassDevsW');
final _enumIfaces = _setup.lookupFunction<Int32 Function(IntPtr, Pointer, Pointer<Uint8>, Uint32, Pointer<Uint8>),
    int Function(int, Pointer, Pointer<Uint8>, int, Pointer<Uint8>)>('SetupDiEnumDeviceInterfaces');
final _ifaceDetail = _setup.lookupFunction<
    Int32 Function(IntPtr, Pointer<Uint8>, Pointer<Uint8>, Uint32, Pointer<Uint32>, Pointer),
    int Function(int, Pointer<Uint8>, Pointer<Uint8>, int, Pointer<Uint32>, Pointer)>('SetupDiGetDeviceInterfaceDetailW');
final _destroyList = _setup.lookupFunction<Int32 Function(IntPtr), int Function(int)>('SetupDiDestroyDeviceInfoList');
final _createFile = _k32.lookupFunction<
    IntPtr Function(Pointer<Utf16>, Uint32, Uint32, Pointer, Uint32, Uint32, IntPtr),
    int Function(Pointer<Utf16>, int, int, Pointer, int, int, int)>('CreateFileW');
final _closeHandle = _k32.lookupFunction<Int32 Function(IntPtr), int Function(int)>('CloseHandle');
final _getAttributes =
    _hid.lookupFunction<Uint8 Function(IntPtr, Pointer<Uint8>), int Function(int, Pointer<Uint8>)>('HidD_GetAttributes');
final _getPreparsed =
    _hid.lookupFunction<Uint8 Function(IntPtr, Pointer<IntPtr>), int Function(int, Pointer<IntPtr>)>('HidD_GetPreparsedData');
final _freePreparsed = _hid.lookupFunction<Uint8 Function(IntPtr), int Function(int)>('HidD_FreePreparsedData');
final _getCaps =
    _hid.lookupFunction<Int32 Function(IntPtr, Pointer<Uint8>), int Function(int, Pointer<Uint8>)>('HidP_GetCaps');
final _setFeature = _hid.lookupFunction<Uint8 Function(IntPtr, Pointer<Uint8>, Uint32),
    int Function(int, Pointer<Uint8>, int)>('HidD_SetFeature');
final _getFeature = _hid.lookupFunction<Uint8 Function(IntPtr, Pointer<Uint8>, Uint32),
    int Function(int, Pointer<Uint8>, int)>('HidD_GetFeature');

const _invalidHandle = -1;

/// An open HID collection.
class HidDevice {
  HidDevice._(this._handle);
  int _handle;

  bool get isOpen => _handle != _invalidHandle;

  /// Opens the first collection matching [vid]/[pid] whose usage page is [usagePage].
  static HidDevice? open(int vid, int pid, int usagePage) {
    return using((arena) {
      final guid = arena<Uint8>(16);
      _hidGuid(guid);
      final devs = _getClassDevs(guid, nullptr, 0, 0x12); // DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
      if (devs == _invalidHandle) return null;
      try {
        final ifd = arena<Uint8>(32); // SP_DEVICE_INTERFACE_DATA (x64)
        final need = arena<Uint32>();
        for (var i = 0;; i++) {
          ifd.cast<Uint32>().value = 32;
          if (_enumIfaces(devs, nullptr, guid, i, ifd) == 0) return null;
          _ifaceDetail(devs, ifd, nullptr, 0, need, nullptr);
          final detail = arena<Uint8>(need.value);
          detail.cast<Uint32>().value = 8; // cbSize of SP_DEVICE_INTERFACE_DETAIL_DATA_W on x64
          if (_ifaceDetail(devs, ifd, detail, need.value, nullptr, nullptr) == 0) continue;
          final path = Pointer<Utf16>.fromAddress(detail.address + 4);
          final h = _createFile(path, 0xC0000000, 3, nullptr, 3, 0, 0); // RW, share RW, OPEN_EXISTING
          if (h == _invalidHandle) continue;
          final attrs = arena<Uint8>(12);
          attrs.cast<Uint32>().value = 12;
          final pp = arena<IntPtr>();
          var match = false;
          if (_getAttributes(h, attrs) != 0) {
            final a = attrs.asTypedList(12).buffer.asByteData();
            if (a.getUint16(4, Endian.little) == vid && a.getUint16(6, Endian.little) == pid &&
                _getPreparsed(h, pp) != 0) {
              final caps = arena<Uint8>(64);
              _getCaps(pp.value, caps);
              _freePreparsed(pp.value);
              match = caps.asTypedList(64).buffer.asByteData().getUint16(2, Endian.little) == usagePage;
            }
          }
          if (match) return HidDevice._(h);
          _closeHandle(h);
        }
      } finally {
        _destroyList(devs);
      }
    });
  }

  /// SET_REPORT(feature): [data] starts with the report ID. False when the device is gone.
  bool setFeature(Uint8List data) => using((arena) {
        final buf = arena<Uint8>(data.length);
        buf.asTypedList(data.length).setAll(0, data);
        return _setFeature(_handle, buf, data.length) != 0;
      });

  /// GET_REPORT(feature) of [length] bytes including the report ID, or null on failure.
  Uint8List? getFeature(int reportId, int length) => using((arena) {
        final buf = arena<Uint8>(length);
        buf.value = reportId;
        if (_getFeature(_handle, buf, length) == 0) return null;
        return Uint8List.fromList(buf.asTypedList(length));
      });

  void close() {
    if (isOpen) _closeHandle(_handle);
    _handle = _invalidHandle;
  }
}
