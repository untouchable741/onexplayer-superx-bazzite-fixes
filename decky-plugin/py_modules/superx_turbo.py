"""Turbo button watcher for ONEXPLAYER SUPER X.

This is a Decky-side workaround only. It does not patch HHD or controller
mappings. When oxpec exposes tt_toggle, the plugin can enable it so the
physical Turbo button emits the keyboard modifier chord:

  LeftCtrl + LeftMeta/LeftGUI + LeftAlt

The watcher uses evdev (/dev/input/event*) because Super X emits standard
keyboard events after tt_toggle=1. It calls the same HHD overlay toggle
function from home_button.py.
"""

import asyncio
import fcntl
import logging
import os
import select
import struct
import time

from home_button import _toggle_hhd_overlay

logger = logging.getLogger("OXP-SuperXTurbo")

_log_info_cb = None
_log_error_cb = None
_log_warning_cb = None
_debug_enabled = False
_last_warning = {}


def set_log_callbacks(info_fn, error_fn, warning_fn):
    global _log_info_cb, _log_error_cb, _log_warning_cb
    _log_info_cb = info_fn
    _log_error_cb = error_fn
    _log_warning_cb = warning_fn


def set_debug_logging(enabled):
    global _debug_enabled
    _debug_enabled = bool(enabled)


def is_debug_logging_enabled():
    return _debug_enabled


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


def _log_debug(msg):
    if _debug_enabled:
        _log_info(f"DEBUG: {msg}")


def _log_warning_rate_limited(key, msg, interval_secs=30.0):
    now = time.monotonic()
    last = _last_warning.get(key, 0.0)
    if now - last >= interval_secs:
        _last_warning[key] = now
        _log_warning(msg)


SUPERX_VENDOR = "ONE-NETBOOK"
SUPERX_BOARD = "ONEXPLAYER SUPER X"

EV_KEY = 0x01
KEY_LEFTCTRL = 29
KEY_LEFTALT = 56
KEY_LEFTMETA = 125
TURBO_KEYS = {KEY_LEFTCTRL, KEY_LEFTMETA, KEY_LEFTALT}
KEY_NAMES = {
    KEY_LEFTCTRL: "KEY_LEFTCTRL",
    KEY_LEFTMETA: "KEY_LEFTMETA",
    KEY_LEFTALT: "KEY_LEFTALT",
}
CHORD_WINDOW_SECS = 0.150
DEBOUNCE_SECS = 0.800
INPUT_EVENT = struct.Struct("llHHi")
TT_TOGGLE_EXACT_PATH = "/sys/devices/platform/oxp-platform/tt_toggle"
TT_TOGGLE_SEARCH_ROOT = "/sys/devices/platform/oxp-platform"
TT_TOGGLE_RETRY_SECS = 5.0
TT_TOGGLE_RETRY_INTERVAL_SECS = 0.25

_IOC_NRBITS = 8
_IOC_TYPEBITS = 8
_IOC_SIZEBITS = 14
_IOC_NRSHIFT = 0
_IOC_TYPESHIFT = _IOC_NRSHIFT + _IOC_NRBITS
_IOC_SIZESHIFT = _IOC_TYPESHIFT + _IOC_TYPEBITS
_IOC_DIRSHIFT = _IOC_SIZESHIFT + _IOC_SIZEBITS
_IOC_READ = 2


def _ioc(direction, type_, nr, size):
    return (
        (direction << _IOC_DIRSHIFT)
        | (type_ << _IOC_TYPESHIFT)
        | (nr << _IOC_NRSHIFT)
        | (size << _IOC_SIZESHIFT)
    )


def _eviocgbit(ev_type, length):
    return _ioc(_IOC_READ, ord("E"), 0x20 + ev_type, length)


def _eviocgname(length):
    return _ioc(_IOC_READ, ord("E"), 0x06, length)


def _read_sysfs_text(path):
    if not path:
        return None
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
    _log_debug(
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

    if not os.path.isdir(TT_TOGGLE_SEARCH_ROOT):
        return paths

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
    if os.path.isdir(TT_TOGGLE_SEARCH_ROOT):
        _log_debug(f"oxp-platform found: {TT_TOGGLE_SEARCH_ROOT}")
    else:
        _log_warning(f"oxp-platform missing: {TT_TOGGLE_SEARCH_ROOT}")

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
            _log_debug(f"tt_toggle found: {path}")
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


def _bit_is_set(buf, bit):
    idx = bit // 8
    if idx >= len(buf):
        return False
    return bool(buf[idx] & (1 << (bit % 8)))


def _event_name(event_path, fd=None):
    name = ""
    close_fd = False
    try:
        if fd is None:
            fd = os.open(event_path, os.O_RDONLY | os.O_NONBLOCK)
            close_fd = True
        buf = bytearray(256)
        fcntl.ioctl(fd, _eviocgname(len(buf)), buf, True)
        name = bytes(buf).split(b"\0", 1)[0].decode(errors="replace")
    except OSError:
        sysfs_name = f"/sys/class/input/{os.path.basename(event_path)}/device/name"
        name = _read_sysfs_text(sysfs_name) or ""
    finally:
        if close_fd and fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
    return name or "unknown"


def _supported_keys(fd):
    buf = bytearray(256)
    fcntl.ioctl(fd, _eviocgbit(EV_KEY, len(buf)), buf, True)
    return {key for key in TURBO_KEYS if _bit_is_set(buf, key)}


def find_evdev_devices():
    devices = []
    input_dir = "/dev/input"
    if not os.path.isdir(input_dir):
        _log_warning(f"evdev input directory not found: {input_dir}")
        return devices

    for name in sorted(os.listdir(input_dir)):
        if not name.startswith("event"):
            continue
        dev_path = os.path.join(input_dir, name)
        try:
            fd = os.open(dev_path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError as e:
            _log_debug(f"evdev candidate inaccessible: {dev_path} error={e}")
            continue

        try:
            dev_name = _event_name(dev_path, fd)
            supported = _supported_keys(fd)
            supported_names = [KEY_NAMES[key] for key in sorted(supported)]
            _log_debug(
                "evdev candidate: "
                f"path={dev_path} name={dev_name!r} supports={supported_names}"
            )
            if TURBO_KEYS.issubset(supported):
                devices.append({"dev_path": dev_path, "name": dev_name})
        except OSError as e:
            _log_debug(f"evdev candidate failed capability scan: {dev_path} error={e}")
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
    return devices


class SuperXTurboMonitor:
    """Async evdev monitor for the Super X Turbo chord."""

    def __init__(self):
        self._task = None
        self._running = False
        self._fds = {}
        self._watched_device_count = 0

    @property
    def is_running(self):
        return self._task is not None and not self._task.done()

    @property
    def watched_device_count(self):
        return self._watched_device_count

    @property
    def task_id(self):
        return id(self._task) if self._task else None

    def status(self):
        return {
            "running": self.is_running,
            "watched_device_count": self._watched_device_count,
            "task_id": self.task_id,
        }

    def _close_fds(self):
        for fd in list(self._fds.keys()):
            try:
                os.close(fd)
            except OSError:
                pass
        self._fds = {}
        self._watched_device_count = 0

    async def _monitor_loop(self):
        self._running = True
        last_trigger = 0.0
        _log_debug(f"Turbo watcher task started id={id(asyncio.current_task())}")

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
            devices = find_evdev_devices()
            if not devices:
                _log_warning_rate_limited(
                    "no_evdev_devices",
                    "No evdev keyboard-capable devices found for Super X Turbo watcher, retrying in 5s",
                )
                await asyncio.sleep(5)
                continue

            fds = {}
            state = {}
            try:
                self._close_fds()
                for dev in devices:
                    try:
                        fd = os.open(dev["dev_path"], os.O_RDONLY | os.O_NONBLOCK)
                        fds[fd] = dev
                        self._fds[fd] = dev
                        state[fd] = {
                            "pressed": set(),
                            "down_times": {},
                            "chord_active": False,
                        }
                        _log_debug(
                            "Selected evdev device for Turbo watcher: "
                            f"path={dev['dev_path']} name={dev['name']!r}"
                        )
                    except OSError as e:
                        _log_warning_rate_limited(
                            f"open_{dev['dev_path']}",
                            f"Could not open {dev['dev_path']}: {e}",
                        )

                if not fds:
                    await asyncio.sleep(5)
                    continue
                self._watched_device_count = len(fds)
                _log_info(f"Super X Turbo watcher active on {self._watched_device_count} evdev device(s)")

                while self._running:
                    ready, _, _ = select.select(list(fds.keys()), [], [], 1.0)
                    if not ready:
                        await asyncio.sleep(0)
                        continue

                    for fd in ready:
                        try:
                            data = os.read(fd, INPUT_EVENT.size * 16)
                        except BlockingIOError:
                            continue
                        except OSError:
                            raise

                        for offset in range(0, len(data) - (len(data) % INPUT_EVENT.size), INPUT_EVENT.size):
                            _, _, ev_type, code, value = INPUT_EVENT.unpack_from(data, offset)
                            if ev_type != EV_KEY or code not in TURBO_KEYS:
                                continue

                            dev = fds[fd]
                            key_name = KEY_NAMES[code]
                            dev_state = state[fd]
                            now = time.monotonic()

                            if value in (1, 2):
                                if code not in dev_state["pressed"]:
                                    _log_debug(f"Turbo key down: {key_name} on {dev['dev_path']}")
                                    dev_state["down_times"][code] = now
                                dev_state["pressed"].add(code)
                            elif value == 0:
                                if code in dev_state["pressed"]:
                                    _log_debug(f"Turbo key up: {key_name} on {dev['dev_path']}")
                                dev_state["pressed"].discard(code)
                                dev_state["down_times"].pop(code, None)
                                dev_state["chord_active"] = False
                                continue
                            else:
                                continue

                            if not TURBO_KEYS.issubset(dev_state["pressed"]):
                                continue
                            times = [dev_state["down_times"].get(key, now) for key in TURBO_KEYS]
                            if max(times) - min(times) > CHORD_WINDOW_SECS:
                                _log_debug("Turbo chord ignored: key timing outside chord window")
                                continue
                            if dev_state["chord_active"]:
                                _log_debug("Turbo chord ignored: chord already active")
                                continue
                            if now - last_trigger < DEBOUNCE_SECS:
                                _log_debug("Turbo chord ignored: debounce active")
                                continue

                            dev_state["chord_active"] = True
                            last_trigger = now
                            _log_info(
                                "Super X Turbo chord detected on "
                                f"{dev['dev_path']} ({dev['name']}); launching HHD overlay"
                            )
                            _toggle_hhd_overlay()
                            _log_info("Overlay launch called via existing HHD state API")
            except OSError as e:
                _log_warning_rate_limited("evdev_changed", f"evdev device changed/disconnected: {e}; retrying in 5s")
                await asyncio.sleep(5)
            finally:
                self._close_fds()
        _log_debug("Turbo watcher loop exited")

    def start(self, loop):
        if self.is_running:
            _log_debug(f"Turbo watcher already running task_id={self.task_id}")
            return False
        self._running = True
        self._task = loop.create_task(self._monitor_loop())
        return True

    async def stop(self):
        self._running = False
        self._close_fds()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._close_fds()
