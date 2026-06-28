"""Turbo button watcher for ONEXPLAYER SUPER X.

This is a Decky-side workaround only. It does not patch HHD or controller
mappings. When oxpec exposes tt_toggle, the plugin can enable it so the
physical Turbo button emits the keyboard modifier chord:

  LeftCtrl + LeftMeta/LeftGUI + LeftAlt

The watcher uses the same hidraw architecture as the Apex Home button monitor
and calls the same HHD overlay toggle function from home_button.py.
"""

import asyncio
import glob
import logging
import os
import select
import time

from home_button import _toggle_hhd_overlay

logger = logging.getLogger("OXP-SuperXTurbo")

_log_info_cb = None
_log_error_cb = None
_log_warning_cb = None


def set_log_callbacks(info_fn, error_fn, warning_fn):
    global _log_info_cb, _log_error_cb, _log_warning_cb
    _log_info_cb = info_fn
    _log_error_cb = error_fn
    _log_warning_cb = warning_fn


def _log_info(msg):
    if _log_info_cb:
        _log_info_cb(msg)
    else:
        logger.info(msg)


def _log_error(msg):
    if _log_error_cb:
        _log_error_cb(msg)
    else:
        logger.error(msg)


def _log_warning(msg):
    if _log_warning_cb:
        _log_warning_cb(msg)
    else:
        logger.warning(msg)


SUPERX_VENDOR = "ONE-NETBOOK"
SUPERX_BOARD = "ONEXPLAYER SUPER X"

# USB VID:PID used by the Apex keyboard macro path. Super X is expected to use
# the same style of hidraw keyboard report, but we fall back to any hidraw node
# so early testers can still validate the chord if the VID/PID differs.
PREFERRED_VID = 0x1A86
PREFERRED_PID = 0xFE00

MOD_LEFTCTRL = 0x01
MOD_LEFTALT = 0x04
MOD_LEFTMETA = 0x08
TURBO_CHORD = MOD_LEFTCTRL | MOD_LEFTALT | MOD_LEFTMETA
DEBOUNCE_SECS = 2.0
TT_TOGGLE_EXACT_PATH = "/sys/devices/platform/oxp-platform/tt_toggle"
TT_TOGGLE_SEARCH_ROOT = "/sys/devices/platform/oxp-platform"
TT_TOGGLE_RETRY_SECS = 5.0
TT_TOGGLE_RETRY_INTERVAL_SECS = 0.25


def _read_sysfs_text(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def get_dmi_info():
    return {
        "board_vendor": _read_sysfs_text("/sys/class/dmi/id/board_vendor"),
        "board_name": _read_sysfs_text("/sys/class/dmi/id/board_name"),
    }


def is_superx():
    dmi = get_dmi_info()
    detected = dmi["board_vendor"] == SUPERX_VENDOR and dmi["board_name"] == SUPERX_BOARD
    _log_info(
        "DMI detected: "
        f"vendor={dmi['board_vendor'] or 'unknown'}, "
        f"board={dmi['board_name'] or 'unknown'}, "
        f"superx={detected}"
    )
    return detected


def find_tt_toggle_paths():
    paths = []
    if os.path.isfile(TT_TOGGLE_EXACT_PATH):
        paths.append(TT_TOGGLE_EXACT_PATH)

    for root, _, files in os.walk(TT_TOGGLE_SEARCH_ROOT):
        if "tt_toggle" not in files:
            continue
        path = os.path.join(root, "tt_toggle")
        if path not in paths:
            paths.append(path)
    return paths


def _wait_for_tt_toggle_paths(timeout_secs=TT_TOGGLE_RETRY_SECS):
    deadline = time.monotonic() + timeout_secs
    while True:
        paths = find_tt_toggle_paths()
        if paths:
            return paths
        if time.monotonic() >= deadline:
            return []
        time.sleep(TT_TOGGLE_RETRY_INTERVAL_SECS)


def enable_tt_toggle(retry=True):
    paths = _wait_for_tt_toggle_paths() if retry else find_tt_toggle_paths()
    if not paths:
        _log_warning(
            "tt_toggle sysfs node not found after oxpec load. "
            f"Checked {TT_TOGGLE_EXACT_PATH} and recursively under {TT_TOGGLE_SEARCH_ROOT}"
        )
        return {"success": False, "error": "tt_toggle not found", "paths": [], "value": None}

    errors = []
    enabled_paths = []
    final_value = None
    for path in paths:
        try:
            before = _read_sysfs_text(path)
            with open(path, "w") as f:
                f.write("1\n")
            after = _read_sysfs_text(path)
            final_value = after
            _log_info(f"tt_toggle enabled: path={path} before={before!r} final={after!r}")
            if after == "1":
                enabled_paths.append(path)
        except OSError as e:
            errors.append(f"{path}: {e}")
            _log_error(f"Failed to enable tt_toggle at {path}: {e}")

    if enabled_paths:
        return {"success": True, "paths": enabled_paths, "value": "1"}
    if errors:
        return {"success": False, "error": "; ".join(errors), "paths": paths, "value": final_value}
    return {
        "success": False,
        "error": f"tt_toggle did not read back as 1; final value: {final_value!r}",
        "paths": paths,
        "value": final_value,
    }


def _hidraw_info(sysfs_path):
    uevent_path = os.path.join(sysfs_path, "device", "uevent")
    info = {"path": sysfs_path, "vid": None, "pid": None, "raw": ""}
    try:
        with open(uevent_path) as f:
            content = f.read()
        info["raw"] = content
    except OSError:
        return info

    for line in content.splitlines():
        if not line.startswith("HID_ID="):
            continue
        parts = line.split(":")
        if len(parts) >= 3:
            try:
                info["vid"] = int(parts[1], 16)
                info["pid"] = int(parts[2], 16)
            except ValueError:
                pass
        break
    return info


def find_hidraw_devices():
    preferred = []
    fallback = []
    for sysfs_path in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        name = os.path.basename(sysfs_path)
        dev_path = f"/dev/{name}"
        if not os.path.exists(dev_path):
            continue
        info = _hidraw_info(sysfs_path)
        item = {"dev_path": dev_path, "vid": info["vid"], "pid": info["pid"]}
        if info["vid"] == PREFERRED_VID and info["pid"] == PREFERRED_PID:
            preferred.append(item)
        else:
            fallback.append(item)
    return preferred + fallback


def _is_turbo_chord(data):
    if not data or len(data) < 8:
        return False
    modifier = data[0]
    keys = data[2:8]
    return (modifier & TURBO_CHORD) == TURBO_CHORD and all(k == 0 for k in keys)


class SuperXTurboMonitor:
    """Async hidraw monitor for the Super X Turbo chord."""

    def __init__(self):
        self._task = None
        self._running = False

    @property
    def is_running(self):
        return self._task is not None and not self._task.done()

    async def _monitor_loop(self):
        self._running = True
        last_trigger = 0.0

        if not is_superx():
            _log_warning("Super X Turbo watcher disabled because DMI does not match ONEXPLAYER SUPER X")
            self._running = False
            return

        tt_result = enable_tt_toggle(retry=False)
        if not tt_result.get("success"):
            _log_warning(
                "Super X Turbo watcher disabled because tt_toggle is not available/enabled: "
                f"{tt_result.get('error', 'unknown')}"
            )
            self._running = False
            return

        while self._running:
            devices = find_hidraw_devices()
            if not devices:
                _log_warning("No hidraw devices found for Super X Turbo watcher, retrying in 5s")
                await asyncio.sleep(5)
                continue

            fds = {}
            try:
                for dev in devices:
                    try:
                        fd = os.open(dev["dev_path"], os.O_RDONLY | os.O_NONBLOCK)
                        fds[fd] = dev
                        _log_info(
                            "Selected hidraw device for Turbo watcher: "
                            f"{dev['dev_path']} vid={dev['vid']} pid={dev['pid']}"
                        )
                    except OSError as e:
                        _log_warning(f"Could not open {dev['dev_path']}: {e}")

                if not fds:
                    await asyncio.sleep(5)
                    continue

                while self._running:
                    ready, _, _ = select.select(list(fds.keys()), [], [], 0.1)
                    if not ready:
                        await asyncio.sleep(0.02)
                        continue

                    for fd in ready:
                        try:
                            data = os.read(fd, 8)
                        except BlockingIOError:
                            continue
                        except OSError:
                            raise

                        if not _is_turbo_chord(data):
                            continue

                        now = time.monotonic()
                        if now - last_trigger < DEBOUNCE_SECS:
                            continue
                        last_trigger = now
                        dev_path = fds[fd]["dev_path"]
                        _log_info(f"Super X Turbo chord detected on {dev_path}; toggling HHD overlay")
                        _toggle_hhd_overlay()
                        _log_info("Overlay command executed via existing HHD state API")
            except OSError as e:
                _log_warning(f"hidraw device changed/disconnected: {e}; retrying in 5s")
                await asyncio.sleep(5)
            finally:
                for fd in list(fds.keys()):
                    try:
                        os.close(fd)
                    except OSError:
                        pass

    def start(self, loop):
        if not self.is_running:
            self._running = True
            self._task = loop.create_task(self._monitor_loop())

    async def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
