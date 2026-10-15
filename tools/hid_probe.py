#!/usr/bin/env python3
"""Read-only HID probe for the Goku 2 in PS5 mode (054C:0CE6): strings, feature
reports 0x09/0x20/0x05 and three input reports. Windows only, no dependencies."""
import ctypes as C, ctypes.wintypes as W, uuid, time, sys
hid=C.WinDLL('hid'); sa=C.WinDLL('setupapi'); k=C.WinDLL('kernel32',use_last_error=True)
class GUID(C.Structure): _fields_=[('d1',W.DWORD),('d2',W.WORD),('d3',W.WORD),('d4',C.c_ubyte*8)]
g=GUID(); hid.HidD_GetHidGuid(C.byref(g))
class IFD(C.Structure): _fields_=[('cb',W.DWORD),('g',GUID),('f',W.DWORD),('r',C.c_void_p)]
sa.SetupDiGetClassDevsW.restype=C.c_void_p
h=sa.SetupDiGetClassDevsW(C.byref(g),None,None,0x12)
paths=[]; i=0
while True:
    d=IFD(); d.cb=C.sizeof(IFD)
    if not sa.SetupDiEnumDeviceInterfaces(C.c_void_p(h),None,C.byref(g),i,C.byref(d)): break
    n=W.DWORD(); sa.SetupDiGetDeviceInterfaceDetailW(C.c_void_p(h),C.byref(d),None,0,C.byref(n),None)
    buf=C.create_string_buffer(n.value); C.cast(buf,C.POINTER(W.DWORD))[0]=8 if C.sizeof(C.c_void_p)==8 else 6
    sa.SetupDiGetDeviceInterfaceDetailW(C.c_void_p(h),C.byref(d),buf,n,None,None)
    paths.append(C.wstring_at(C.addressof(buf)+4)); i+=1
k.CreateFileW.restype=C.c_void_p
for p in paths:
    if 'vid_054c&pid_0ce6' not in p.lower(): continue
    print('PATH',p)
    hd=k.CreateFileW(p,0xC0000000,3,None,3,0,None)
    if hd in (None,C.c_void_p(-1).value): hd=k.CreateFileW(p,0,3,None,3,0,None); print(' (no rw access)')
    s=C.create_unicode_buffer(256)
    for nm,fn in (('manufacturer',hid.HidD_GetManufacturerString),('product',hid.HidD_GetProductString),('serial',hid.HidD_GetSerialNumberString)):
        print(' ',nm, fn(C.c_void_p(hd),s,512) and s.value)
    for rid,ln in ((0x09,20),(0x20,64),(0x05,41)):
        b=(C.c_ubyte*ln)(); b[0]=rid
        ok=hid.HidD_GetFeature(C.c_void_p(hd),b,ln)
        print(f'  feature 0x{rid:02x}', bytes(b).hex(' ') if ok else f'fail {C.get_last_error()}')
    if 'mi_03' in p.lower():
        b=(C.c_ubyte*64)(); n=W.DWORD()
        for _ in range(3):
            if k.ReadFile(C.c_void_p(hd),b,64,C.byref(n),None): print('  input',bytes(b[:n.value]).hex(' '))
    k.CloseHandle(C.c_void_p(hd))
