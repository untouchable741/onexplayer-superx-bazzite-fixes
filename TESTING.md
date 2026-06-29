# ONEXPLAYER SUPER X v0.9-beta Testing

Tested baseline:

- Device: ONEXPLAYER SUPER X
- OS: Bazzite Stable 43
- Kernel: `6.17.7-ba29.fc43.x86_64`

Install `decky-plugin/OneXPlayer_Super_X_Tools.zip` through Decky Loader.

## Verification

```bash
uname -r
modinfo oxpec | grep -i super
lsmod | grep oxpec
cat /sys/devices/platform/oxp-platform/tt_toggle
find /sys -iname "*tt_toggle*" -o -iname "*charge*limit*" -o -iname "*bypass*" -o -iname "*fan*" 2>/dev/null
```

Expected:

- `oxpec` is loaded.
- `/sys/devices/platform/oxp-platform/tt_toggle` exists and reads `1`.
- `/sys/devices/platform/oxp-platform/hwmon/hwmon*/fan1_input` exists.
- Charge limit and charge behaviour/bypass nodes appear under power supply sysfs.

## Checklist

- Reboot.
- Suspend/resume.
- Toggle **EC Sensor Driver (oxpec)**.
- Confirm fan control changes RPM in HHD.
- Confirm charge limit changes the sysfs value.
- Confirm bypass works while plugged in.
- Enable **Turbo -> HHD Overlay**.
- Press Turbo and confirm HHD overlay opens.
- Press external keyboard `Ctrl + Meta + Alt` and confirm it also opens overlay.
  This is intentional/known behavior for v0.9-beta.
- Confirm normal typing does not spam logs with Debug logging off.
- Toggle **Debug logging** on/off and confirm it does not spawn duplicate watchers.
- Confirm kernel mismatch warning appears when the bundled module does not match
  `uname -r`.
- Press **Rebuild oxpec** and confirm rebuild succeeds if kernel headers/build
  tools are available.

## Rebuild Prerequisites

The plugin checks for these before rebuilding:

```bash
test -d /lib/modules/$(uname -r)/build
command -v make
command -v gcc || command -v cc
```

It runs:

```bash
make -C /lib/modules/$(uname -r)/build M=<plugin>/py_modules/oxpec/build modules
```

The plugin does not install packages automatically.

## Logs

```bash
sudo tail -n 150 ~/homebrew/logs/ONEXPLAYER\ SUPER\ X\ Tools/oxp-superx.log
```

Look for:

- Super X DMI detection.
- oxpec load method.
- kernel mismatch or vermagic match.
- `tt_toggle` path/value.
- fan and charge paths.
- Turbo chord detected.
- HHD overlay launch result.

Debug logging is off by default. Enable it only for troubleshooting. With debug
enabled, logs may include evdev candidates, selected devices, key down/up events,
debounce state, and full HHD API request/response details.

If keyboard input becomes laggy:

1. Disable **Debug logging**.
2. Disable **Turbo -> HHD Overlay**.
3. Restart Decky's plugin loader:

```bash
sudo systemctl restart plugin_loader.service
```

## TDP Safety

Do not use 120W. ONEXPLAYER Super X official Windows limits are 75W on AC power
and 55W on battery. v0.9-beta does not modify HHD TDP behavior.
