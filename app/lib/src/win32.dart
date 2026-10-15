// Small Win32 helpers through dart:ffi (no plugins): file dialogs, opening links,
// and finding the adapter's update-mode drive.
import 'dart:ffi';
import 'dart:io';

import 'package:ffi/ffi.dart';

final _comdlg = DynamicLibrary.open('comdlg32.dll');
final _shell = DynamicLibrary.open('shell32.dll');
final _k32 = DynamicLibrary.open('kernel32.dll');

final _getOpen = _comdlg.lookupFunction<Int32 Function(Pointer<Uint8>), int Function(Pointer<Uint8>)>('GetOpenFileNameW');
final _getSave = _comdlg.lookupFunction<Int32 Function(Pointer<Uint8>), int Function(Pointer<Uint8>)>('GetSaveFileNameW');
final _shellExecute = _shell.lookupFunction<
    IntPtr Function(IntPtr, Pointer<Utf16>, Pointer<Utf16>, Pointer<Utf16>, Pointer<Utf16>, Int32),
    int Function(int, Pointer<Utf16>, Pointer<Utf16>, Pointer<Utf16>, Pointer<Utf16>, int)>('ShellExecuteW');
final _getVolumeInfo = _k32.lookupFunction<
    Int32 Function(Pointer<Utf16>, Pointer<Utf16>, Uint32, Pointer, Pointer, Pointer, Pointer<Utf16>, Uint32),
    int Function(Pointer<Utf16>, Pointer<Utf16>, int, Pointer, Pointer, Pointer, Pointer<Utf16>, int)>(
    'GetVolumeInformationW');
final _getDrives = _k32.lookupFunction<Uint32 Function(), int Function()>('GetLogicalDrives');

/// Common file dialog. [filter] pairs: ('Firmware (*.bin;*.zip)', '*.bin;*.zip').
String? _fileDialog({required bool save, required List<(String, String)> filter, String? defaultName, String? ext}) {
  return using((arena) {
    // OPENFILENAMEW on x64 is 152 bytes
    final ofn = arena<Uint8>(152);
    final file = arena<Uint16>(1024);
    if (defaultName != null) {
      final units = defaultName.codeUnits;
      for (var i = 0; i < units.length && i < 1023; i++) {
        file[i] = units[i];
      }
    }
    final f = StringBuffer();
    for (final (desc, pattern) in filter) {
      f
        ..write(desc)
        ..write('\u0000')
        ..write(pattern)
        ..write('\u0000');
    }
    f.write('\u0000');
    final filterPtr = f.toString().toNativeUtf16(allocator: arena);
    void u32(int off, int v) => (ofn + off).cast<Uint32>().value = v;
    void ptr(int off, Pointer p) => (ofn + off).cast<IntPtr>().value = p.address;
    u32(0, 152); // lStructSize
    ptr(24, filterPtr); // lpstrFilter
    u32(44, 1); // nFilterIndex
    ptr(48, file); // lpstrFile
    u32(56, 1024); // nMaxFile
    // Flags: OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR, or OVERWRITEPROMPT for save
    u32(96, save ? 0x00000002 | 0x00000800 | 0x00000008 : 0x00001000 | 0x00000800 | 0x00000008);
    if (ext != null) ptr(104, ext.toNativeUtf16(allocator: arena)); // lpstrDefExt
    final ok = save ? _getSave(ofn) : _getOpen(ofn);
    return ok != 0 ? file.cast<Utf16>().toDartString() : null;
  });
}

String? pickFirmwareFile() => _fileDialog(
      save: false,
      filter: [('Goku 2 firmware (*.bin, *.zip)', '*.bin;*.zip'), ('All files', '*.*')],
    );

String? pickSaveLocation(String name) =>
    _fileDialog(save: true, filter: [('Firmware (*.bin)', '*.bin')], defaultName: name, ext: 'bin');

void openUrl(String url) => using((arena) {
      _shellExecute(0, 'open'.toNativeUtf16(allocator: arena), url.toNativeUtf16(allocator: arena), nullptr,
          nullptr, 1);
    });

/// Root of a mounted drive whose volume label starts with "GuliKit" (the adapter in update mode).
String? findUpdateDrive() {
  final mask = _getDrives();
  for (var i = 2; i < 26; i++) {
    if (mask & (1 << i) == 0) continue;
    final root = '${String.fromCharCode(65 + i)}:\\';
    final label = using((arena) {
      final buf = arena<Uint16>(64);
      final ok = _getVolumeInfo(root.toNativeUtf16(allocator: arena), buf.cast<Utf16>(), 64, nullptr, nullptr,
          nullptr, nullptr, 0);
      return ok != 0 ? buf.cast<Utf16>().toDartString() : '';
    });
    if (label.toLowerCase().startsWith('gulikit') && Directory(root).existsSync()) return root;
  }
  return null;
}
