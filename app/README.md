# Super Saiyan Companion

Desktop companion app for the Goku 2 Adapter Super Saiyan Mod firmware (Flutter,
Material 3, Windows). It talks to the adapter's config channel (HID feature report 2,
see `mods/super_saiyan/config.c`) through the Windows HID API with `dart:ffi`, so it
needs no plugins and no drivers.

```bash
flutter build windows --release   # -> build/windows/x64/runner/Release/
```

`SS_SCREENSHOT_DIR=<dir>` renders every page with demo data into PNGs and exits (used
for the screenshots in the main README).
