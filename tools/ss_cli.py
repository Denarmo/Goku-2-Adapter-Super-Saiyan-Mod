#!/usr/bin/env python3
"""Command-line client for the super_saiyan config channel (Windows, no extra packages).

The adapter must run the super_saiyan mod in Xbox 360 mode; it then shows up as
1209:0001 with a vendor HID collection (usage page 0xFF00) that carries feature
report 2. Protocol: see mods/super_saiyan/config.c.

    python tools/ss_cli.py info
    python tools/ss_cli.py get                      # all settings
    python tools/ss_cli.py set tm_hold_ms=400 tm_flags=1
    python tools/ss_cli.py save | defaults | live
"""
import ctypes as C
import ctypes.wintypes as W
import struct
import sys

VID, PID = 0x1209, 0x0001
# name: (offset, struct format) - keep in sync with mods/super_saiyan/ss.h
FIELDS = {
    "version": (0, "B"), "size": (1, "B"),
    "tm_enable": (2, "B"), "tm_speed": (3, "B"), "tm_scroll_div": (4, "B"), "tm_flags": (5, "B"),
    "tm_slop": (6, "H"), "tm_drag_slop": (8, "H"), "tm_hold_ms": (10, "H"),
    "remap": (12, "20s"), "turbo_mask": (32, "I"), "turbo_rate": (36, "B"), "toggle_mask": (37, "I"),
    "socd": (41, "B"), "stick_dz": (42, "2s"), "stick_anti_dz": (44, "2s"), "stick_curve": (46, "2s"),
    "stick_flags": (48, "B"), "trig_dz": (49, "2s"), "trig_flags": (51, "B"),
}

hid, setup, k32 = C.WinDLL("hid"), C.WinDLL("setupapi"), C.WinDLL("kernel32")


class GUID(C.Structure):
    _fields_ = [("a", W.DWORD), ("b", W.WORD), ("c", W.WORD), ("d", C.c_ubyte * 8)]


class IFDATA(C.Structure):
    _fields_ = [("cb", W.DWORD), ("guid", GUID), ("flags", W.DWORD), ("res", C.c_void_p)]


class ATTRS(C.Structure):
    _fields_ = [("cb", W.ULONG), ("vid", W.USHORT), ("pid", W.USHORT), ("ver", W.USHORT)]


class CAPS(C.Structure):
    _fields_ = [("usage", W.USHORT), ("page", W.USHORT), ("inlen", W.USHORT), ("outlen", W.USHORT),
                ("featlen", W.USHORT), ("res", W.USHORT * 17), ("n", W.USHORT * 10)]


k32.CreateFileW.restype = C.c_void_p
setup.SetupDiGetClassDevsW.restype = C.c_void_p


def open_device():
    g = GUID()
    hid.HidD_GetHidGuid(C.byref(g))
    devs = setup.SetupDiGetClassDevsW(C.byref(g), None, None, 0x12)
    i = 0
    while True:
        ifd = IFDATA(cb=C.sizeof(IFDATA))
        if not setup.SetupDiEnumDeviceInterfaces(C.c_void_p(devs), None, C.byref(g), i, C.byref(ifd)):
            break
        i += 1
        need = W.DWORD()
        setup.SetupDiGetDeviceInterfaceDetailW(C.c_void_p(devs), C.byref(ifd), None, 0, C.byref(need), None)
        buf = C.create_string_buffer(need.value)
        C.cast(buf, C.POINTER(W.DWORD))[0] = 8 if C.sizeof(C.c_void_p) == 8 else 6
        if not setup.SetupDiGetDeviceInterfaceDetailW(C.c_void_p(devs), C.byref(ifd), buf, need, None, None):
            continue
        path = C.wstring_at(C.addressof(buf) + 4)
        h = k32.CreateFileW(path, 0xC0000000, 3, None, 3, 0, None)
        if not h or h == C.c_void_p(-1).value:
            continue
        a = ATTRS(cb=C.sizeof(ATTRS))
        hid.HidD_GetAttributes(C.c_void_p(h), C.byref(a))
        pp = C.c_void_p()
        caps = CAPS()
        if a.vid == VID and a.pid == PID and hid.HidD_GetPreparsedData(C.c_void_p(h), C.byref(pp)):
            hid.HidP_GetCaps(pp, C.byref(caps))
            hid.HidD_FreePreparsedData(pp)
            if caps.page == 0xFF00:
                return h
        k32.CloseHandle(C.c_void_p(h))
    sys.exit("adapter not found: needs the super_saiyan firmware, Xbox 360 mode, plugged in")


def cmd(h, c, a0=0, a1=0, data=b""):
    out = (bytes([2, c, a0, a1]) + data).ljust(64, b"\0")
    if not hid.HidD_SetFeature(C.c_void_p(h), out, 64):
        sys.exit(f"SetFeature failed ({k32.GetLastError()})")
    buf = C.create_string_buffer(b"\x02" + bytes(63), 64)
    if not hid.HidD_GetFeature(C.c_void_p(h), buf, 64):
        sys.exit(f"GetFeature failed ({k32.GetLastError()})")
    r = buf.raw
    if r[1] != c or r[2] != 0:
        sys.exit(f"command {c} failed: {r[:8].hex(' ')}")
    return r


def read_settings(h, size):
    data = b""
    while len(data) < size:
        n = min(58, size - len(data))
        data += cmd(h, 2, len(data), n)[5:5 + n]
    return bytearray(data)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    h = open_device()
    r = cmd(h, 1)
    size = r[6]
    what = sys.argv[1]
    if what == "info":
        print(f"protocol {r[3]}, mod firmware {r[5]}.{r[4]:02x}, settings {size} bytes, "
              f"output mode {r[7]}, controller type {r[8]}")
    elif what == "get":
        s = read_settings(h, size)
        for name, (off, fmt) in FIELDS.items():
            v = struct.unpack_from("<" + fmt, s, off)[0]
            print(f"{name:14} {list(v) if isinstance(v, bytes) else v}")
    elif what == "set":
        s = read_settings(h, size)
        for kv in sys.argv[2:]:
            name, val = kv.split("=", 1)
            off, fmt = FIELDS[name]
            v = bytes(int(x, 0) for x in val.split(",")) if fmt.endswith("s") else int(val, 0)
            struct.pack_into("<" + fmt, s, off, v)
            n = struct.calcsize(fmt)
            cmd(h, 3, off, n, bytes(s[off:off + n]))
        print("applied (not saved; run 'save' to keep it)")
    elif what == "save":
        cmd(h, 4)
        print("saved")
    elif what == "defaults":
        cmd(h, 5)
        print("defaults restored (not saved)")
    elif what == "live":
        r = cmd(h, 6)[3:]
        t, ts, b = struct.unpack_from("<III", r, 0)
        lx, ly, rx, ry, zl, zr = struct.unpack_from("<hhhhHH", r, 0x0C)
        print(f"type {t} buttons {b:08x} L({lx},{ly}) R({rx},{ry}) ZL {zl} ZR {zr}")
    else:
        sys.exit(__doc__)
    k32.CloseHandle(C.c_void_p(h))


if __name__ == "__main__":
    main()
