# ONEXPLAYER SUPER X — Bazzite oxpec Test Plugin

A Decky Loader plugin variant for early ONEXPLAYER SUPER X testing on Bazzite.

This v0.1 build is intentionally narrow: it validates `oxpec` EC driver recognition,
module loading, fan hwmon nodes, and charge-related sysfs controls.

## Scope

Included:

- Adds the `ONEXPLAYER SUPER X` DMI entry to the bundled `oxpec.c` source.
- Installs/loads a bundled `oxpec.ko` that matches the running kernel.
- Falls back through `modprobe`, bundled `insmod`, and `/var/lib/oxpec/oxpec.ko`.
- Shows whether fan, charge, and turbo-takeover sysfs nodes are detected.
- Enables `tt_toggle=1` when available and watches the Turbo keyboard chord
  `LeftCtrl + LeftMeta/LeftGUI + LeftAlt` to toggle the existing HHD overlay.

Not included in v0.1:

- Apex HHD/controller mapping patches.
- Back-paddle firmware remapping.
- Sleep, resume, and speaker DSP fixes.

Those Apex-specific modules remain in the repository for reference, but the Super X
plugin UI, startup path, and package output do not apply HHD patches.

## Super X oxpec DMI Patch

The bundled driver source adds:

```c
{
	.matches = {
		DMI_MATCH(DMI_BOARD_VENDOR, "ONE-NETBOOK"),
		DMI_EXACT_MATCH(DMI_BOARD_NAME, "ONEXPLAYER SUPER X"),
	},
	.driver_data = (void *)oxp_fly,
},
```

## Build

From the plugin directory:

```bash
cd decky-plugin
bun install
bun run build
bun run package
```

`bun run package` now refuses to package stale `oxpec.ko` files that do not
contain `ONEXPLAYER SUPER X`.

## Rebuild oxpec.ko On Bazzite

Run this on the target Super X/Bazzite device, not on macOS:

```bash
./scripts/build-oxpec-on-bazzite.sh
cd decky-plugin
bun run package
```

The package command creates:

```text
decky-plugin/OneXPlayer_Super_X_Tools.zip
```

## Install

Install through Decky Developer Mode, or manually:

```bash
sudo unzip -o decky-plugin/OneXPlayer_Super_X_Tools.zip -d ~/homebrew/plugins/
sudo systemctl restart plugin_loader.service
```

## Test On Bazzite

After installing and toggling on the EC Sensor Driver in Decky, run:

```bash
uname -r
modinfo oxpec | grep -i "super\|onex\|one-netbook"
lsmod | grep oxpec
sudo dmesg | grep -Ei "oxpec|onex|one.?netbook|super"
find /sys -iname "*tt_toggle*" -o -iname "*charge*limit*" -o -iname "*bypass*" -o -iname "*fan*" 2>/dev/null
```

Then enable **Turbo -> HHD Overlay** in the plugin, press the physical Turbo
button, and confirm the HHD overlay toggles once per press.

Useful Decky log:

```bash
sudo tail -n 100 ~/homebrew/logs/ONEXPLAYER\ SUPER\ X\ Tools/oxp-superx.log
```

If the running Bazzite kernel does not match one of the bundled module folders under
`decky-plugin/py_modules/oxpec/`, rebuild `oxpec.ko` on the target kernel and add it
under `decky-plugin/py_modules/oxpec/$(uname -r)/oxpec.ko`.
