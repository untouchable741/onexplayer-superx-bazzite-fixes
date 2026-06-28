# ONEXPLAYER SUPER X Tools v0.9-beta

Decky Loader preview plugin for ONEXPLAYER SUPER X on Bazzite.

Supported device: ONEXPLAYER SUPER X only.

Tested:

- OS: Bazzite Stable 43
- Kernel: `6.17.7-ba29.fc43.x86_64`
- HHD: stock/unpatched

## Features

- Loads patched `oxpec.ko` with ONEXPLAYER SUPER X DMI support.
- Shows fan, charge, bypass, and `tt_toggle` sysfs paths.
- Sets `/sys/devices/platform/oxp-platform/tt_toggle` to `1`.
- Watches evdev for Turbo's `Ctrl + Meta + Alt` chord and opens the HHD overlay.
- Detects kernel/module mismatch and can rebuild `oxpec.ko` on-device when kernel
  headers and build tools are already installed.

## Not Included

- No HHD package patching.
- No Apex controller/button mapping patches on Super X.
- No HHD TDP changes.

## TDP Safety

ONEXPLAYER Super X official Windows limits are:

- AC power: 75W max
- Battery: 55W max

Do not use 120W even if HHD exposes it. A future release should add a
Super X-specific HHD TDP profile.

## Known Behavior

External keyboard `Ctrl + Meta + Alt` also opens the HHD overlay in v0.9-beta.
This is intentional for this preview; the watcher does not restrict by keyboard
device yet.

## Build

```bash
cd decky-plugin
bun install
bun run build
bun run package
```

Package output:

```text
decky-plugin/OneXPlayer_Super_X_Tools.zip
```

## Install

Install the zip through Decky Loader Developer Mode, or manually:

```bash
sudo unzip -o decky-plugin/OneXPlayer_Super_X_Tools.zip -d ~/homebrew/plugins/
sudo systemctl restart plugin_loader.service
```

## Kernel Mismatch / Rebuild

The bundled module must match `uname -r`. If the plugin shows:

```text
Kernel mismatch. Rebuild oxpec.ko for current kernel.
```

use the **Rebuild oxpec** button.

The rebuild requires these to already exist on the device:

- `/lib/modules/$(uname -r)/build`
- `make`
- `gcc` or `cc`

The plugin does not install packages automatically.

## Verification Commands

```bash
uname -r
modinfo oxpec | grep -i super
lsmod | grep oxpec
cat /sys/devices/platform/oxp-platform/tt_toggle
find /sys -iname "*tt_toggle*" -o -iname "*charge*limit*" -o -iname "*bypass*" -o -iname "*fan*" 2>/dev/null
```

Useful log:

```bash
sudo tail -n 150 ~/homebrew/logs/ONEXPLAYER\ SUPER\ X\ Tools/oxp-superx.log
```

## v0.9-beta Checklist

- Reboot and confirm oxpec loads.
- Suspend/resume and confirm sysfs nodes still appear.
- Turbo opens the HHD overlay.
- External keyboard `Ctrl + Meta + Alt` opens the HHD overlay intentionally.
- Fan control changes RPM in HHD.
- Charge limit changes the sysfs value.
- Bypass works while plugged in.
- Kernel mismatch warning appears when no matching module exists.
- Rebuild oxpec works when kernel headers/build tools are available.
