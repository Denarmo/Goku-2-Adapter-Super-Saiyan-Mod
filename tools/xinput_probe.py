#!/usr/bin/env python3
"""Log XInput button changes (Windows) for N seconds - used to check mods on hardware
when the adapter is in Xbox 360 output mode.  usage: xinput_probe.py [seconds]"""
import ctypes as C, sys, time
class GP(C.Structure): _fields_ = [("wButtons", C.c_ushort), ("lt", C.c_ubyte), ("rt", C.c_ubyte),
                                   ("lx", C.c_short), ("ly", C.c_short), ("rx", C.c_short), ("ry", C.c_short)]
class ST(C.Structure): _fields_ = [("pkt", C.c_uint), ("gp", GP)]
x = C.WinDLL("xinput1_4")
NAMES = {0x1000: "A", 0x2000: "B", 0x4000: "X", 0x8000: "Y", 0x0100: "LB", 0x0200: "RB",
         0x0010: "START", 0x0020: "BACK", 0x0040: "LS", 0x0080: "RS", 0x0400: "GUIDE",
         0x0001: "UP", 0x0002: "DOWN", 0x0004: "LEFT", 0x0008: "RIGHT"}
dur = float(sys.argv[1]) if len(sys.argv) > 1 else 15
end, last, s = time.time() + dur, None, ST()
pads = [i for i in range(4) if x.XInputGetState(i, C.byref(s)) == 0]
print("pads:", pads, flush=True)
while time.time() < end and pads:
    x.XInputGetState(pads[0], C.byref(s))
    b = s.gp.wButtons
    if b != last:
        print(f"{time.strftime('%H:%M:%S')} buttons={b:04x} {'+'.join(n for m, n in NAMES.items() if b & m) or '-'}", flush=True)
        last = b
    time.sleep(0.01)
