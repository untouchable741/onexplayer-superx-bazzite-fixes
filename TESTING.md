# ONEXPLAYER SUPER X Bazzite Testing

Install `decky-plugin/OneXPlayer_Super_X_Tools.zip`, toggle on **EC Sensor Driver
(oxpec)** in Decky, then run:

Before packaging on Bazzite, rebuild the kernel module:

```bash
./scripts/build-oxpec-on-bazzite.sh
cd decky-plugin
bun run package
```

```bash
uname -r
modinfo oxpec | grep -i "super\|onex\|one-netbook"
lsmod | grep oxpec
sudo dmesg | grep -Ei "oxpec|onex|one.?netbook|super"
find /sys -iname "*tt_toggle*" -o -iname "*charge*limit*" -o -iname "*bypass*" -o -iname "*fan*" 2>/dev/null
```

Then enable **Turbo -> HHD Overlay** in Decky and press the physical Turbo button.
The expected result is one HHD overlay toggle per press. The log should include:

- detected Super X DMI
- `tt_toggle` path/value or a warning that it was not found
- selected hidraw device
- Turbo chord detected
- overlay command executed

Expected signals:

- `lsmod` shows `oxpec`.
- `dmesg` includes oxpec loading/probe output.
- `/sys/class/hwmon/...` exposes fan/PWM nodes such as `fan1_input`, `pwm1`,
  and `pwm1_enable`.
- `/sys/class/power_supply/...` may expose charge behavior/threshold nodes if the
  battery extension registered successfully.

This v0.1 package does not enable Apex HHD/controller patches. Turbo overlay is
handled by the Decky hidraw watcher only.
