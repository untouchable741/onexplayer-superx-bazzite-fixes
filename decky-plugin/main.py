"""ONEXPLAYER SUPER X Tools — Decky Loader plugin backend.

For v0.9-beta this plugin focuses Super X support on oxpec EC loading,
fan/charge sysfs detection, tt_toggle, and Turbo-to-HHD overlay handling.

Each async method in the Plugin class becomes an RPC endpoint that
the React frontend can call via @decky/api's `callable()`.
"""

import asyncio
import json
import os
import subprocess
import sys

# Official Decky module — injected by the loader at runtime.
# Provides DECKY_PLUGIN_DIR, DECKY_PLUGIN_LOG_DIR, and logger.
import decky

# Add py_modules to path so we can import our helper modules
sys.path.insert(0, os.path.join(decky.DECKY_PLUGIN_DIR, "py_modules"))

# Import helper modules with error handling so a single broken module
# doesn't crash the entire plugin on load.

try:
    import button_fix as _button_fix_mod
    from button_fix import (
        apply as apply_button_fix_impl,
        revert as revert_button_fix_impl,
        is_applied as button_fix_status,
    )
except Exception as e:
    decky.logger.error(f"Failed to import button_fix: {e}")
    _button_fix_mod = None
    apply_button_fix_impl = None
    revert_button_fix_impl = None
    button_fix_status = None

try:
    import back_paddle as _back_paddle_mod
    from back_paddle import BackPaddleMonitor
except Exception as e:
    decky.logger.error(f"Failed to import back_paddle: {e}")
    _back_paddle_mod = None
    BackPaddleMonitor = None

try:
    import sleep_fix as _sleep_fix_mod
    from sleep_fix import (
        get_status as sleep_fix_status,
        apply as apply_light_sleep_impl,
        revert as revert_light_sleep_impl,
        remove as remove_sleep_fix_impl,
    )
except Exception as e:
    decky.logger.error(f"Failed to import sleep_fix: {e}")
    _sleep_fix_mod = None
    sleep_fix_status = None
    apply_light_sleep_impl = None
    revert_light_sleep_impl = None
    remove_sleep_fix_impl = None

try:
    import speaker_dsp as _speaker_dsp_mod
    from speaker_dsp import (
        enable as enable_speaker_dsp_impl,
        disable as disable_speaker_dsp_impl,
        set_profile as set_dsp_profile_impl,
        get_status as speaker_dsp_status,
        list_profiles as list_dsp_profiles_impl,
        get_preset_bands as get_preset_bands_impl,
        get_custom_profiles as get_custom_profiles_impl,
        save_custom_profile as save_custom_profile_impl,
        delete_custom_profile as delete_custom_profile_impl,
        play_test_sound as play_test_sound_impl,
        stop_test_sound as stop_test_sound_impl,
        bypass as bypass_speaker_dsp_impl,
        unbypass as unbypass_speaker_dsp_impl,
        is_bypassed as is_bypassed_speaker_dsp_impl,
    )
except Exception as e:
    decky.logger.error(f"Failed to import speaker_dsp: {e}")
    _speaker_dsp_mod = None
    enable_speaker_dsp_impl = None
    disable_speaker_dsp_impl = None
    set_dsp_profile_impl = None
    speaker_dsp_status = None
    list_dsp_profiles_impl = None
    get_preset_bands_impl = None
    get_custom_profiles_impl = None
    save_custom_profile_impl = None
    delete_custom_profile_impl = None
    play_test_sound_impl = None
    stop_test_sound_impl = None
    bypass_speaker_dsp_impl = None
    unbypass_speaker_dsp_impl = None
    is_bypassed_speaker_dsp_impl = None

try:
    import home_button as _home_button_mod
    from home_button import HomeButtonMonitor
except Exception as e:
    decky.logger.error(f"Failed to import home_button: {e}")
    _home_button_mod = None
    HomeButtonMonitor = None

try:
    import superx_turbo as _superx_turbo_mod
    from superx_turbo import (
        SuperXTurboMonitor,
        enable_tt_toggle as enable_tt_toggle_impl,
        find_tt_toggle_paths,
        get_dmi_info as get_superx_dmi_info,
        is_superx as is_superx_device,
    )
except Exception as e:
    decky.logger.error(f"Failed to import superx_turbo: {e}")
    _superx_turbo_mod = None
    SuperXTurboMonitor = None
    enable_tt_toggle_impl = None
    find_tt_toggle_paths = None
    get_superx_dmi_info = None
    is_superx_device = None

try:
    import oxpec_loader as _oxpec_mod
    from oxpec_loader import (
        apply as apply_oxpec_impl,
        revert as revert_oxpec_impl,
        is_applied as oxpec_status,
        ensure_loaded as ensure_oxpec_loaded,
        rebuild_for_current_kernel as rebuild_oxpec_impl,
    )
except Exception as e:
    decky.logger.error(f"Failed to import oxpec_loader: {e}")
    _oxpec_mod = None
    apply_oxpec_impl = None
    revert_oxpec_impl = None
    oxpec_status = None
    ensure_oxpec_loaded = None
    rebuild_oxpec_impl = None

try:
    import resume_fix as _resume_fix_mod
    from resume_fix import (
        apply as apply_resume_fix_impl,
        revert as revert_resume_fix_impl,
        is_applied as resume_fix_status,
    )
except Exception as e:
    decky.logger.error(f"Failed to import resume_fix: {e}")
    _resume_fix_mod = None
    apply_resume_fix_impl = None
    revert_resume_fix_impl = None
    resume_fix_status = None

try:
    import xhci_recovery as _xhci_recovery_mod
    from xhci_recovery import check_and_recover as xhci_check_and_recover
except Exception as e:
    decky.logger.error(f"Failed to import xhci_recovery: {e}")
    _xhci_recovery_mod = None
    xhci_check_and_recover = None

try:
    import sleep_enable as _sleep_enable_mod
    from sleep_enable import (
        apply as apply_sleep_enable_impl,
        revert as revert_sleep_enable_impl,
        is_applied as sleep_enable_status,
    )
except Exception as e:
    decky.logger.error(f"Failed to import sleep_enable: {e}")
    _sleep_enable_mod = None
    apply_sleep_enable_impl = None
    revert_sleep_enable_impl = None
    sleep_enable_status = None




def _get_user_home():
    """Get the real (non-root) user's home directory.

    Decky runs as root, so os.path.expanduser("~") returns /root.
    We find the actual user by checking SUDO_USER, the plugin dir path,
    or falling back to the first user in /home.
    """
    # Check SUDO_USER first
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user and sudo_user != "root":
        home = f"/home/{sudo_user}"
        if os.path.isdir(home):
            return home

    # Infer from Decky plugin dir path (e.g. /home/srsholmes/homebrew/plugins/...)
    plugin_dir = decky.DECKY_PLUGIN_DIR
    if plugin_dir.startswith("/home/"):
        parts = plugin_dir.split("/")
        if len(parts) >= 3:
            home = f"/home/{parts[2]}"
            if os.path.isdir(home):
                return home

    # Fallback: first non-root user in /home
    try:
        for name in sorted(os.listdir("/home")):
            path = f"/home/{name}"
            if os.path.isdir(path) and name != "root":
                return path
    except OSError:
        pass

    return os.path.expanduser("~")


# Log file path — write to Decky's plugin log directory
LOG_FILE = os.path.join(decky.DECKY_PLUGIN_LOG_DIR, "oxp-superx.log")
SETTINGS_FILE = os.path.join(decky.DECKY_PLUGIN_LOG_DIR, "settings.json")


def _log_to_file(msg: str):
    """Append a message to our log file (in addition to decky.logger)."""
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f:
            from datetime import datetime
            f.write(f"{datetime.now().isoformat()} [OXP-SuperX] {msg}\n")
    except Exception:
        pass


def _log_info(msg: str):
    decky.logger.info(msg)
    _log_to_file(msg)


def _log_error(msg: str):
    decky.logger.error(msg)
    _log_to_file(f"ERROR: {msg}")


def _log_warning(msg: str):
    decky.logger.warning(msg)
    _log_to_file(f"WARN: {msg}")


def _set_helper_debug_logging(enabled: bool):
    for mod in (_home_button_mod, _superx_turbo_mod):
        if mod and hasattr(mod, "set_debug_logging"):
            try:
                mod.set_debug_logging(enabled)
            except Exception as e:
                _log_warning(f"Failed to set debug logging on {mod.__name__}: {e}")


# Wire log callbacks into helper modules so their logs appear in oxp-superx.log
if _button_fix_mod:
    _button_fix_mod.set_log_callbacks(_log_info, _log_error, _log_warning)
if _back_paddle_mod:
    _back_paddle_mod.set_log_callbacks(_log_info, _log_error, _log_warning)
if _home_button_mod:
    _home_button_mod.set_log_callbacks(_log_info, _log_error, _log_warning)
if _superx_turbo_mod:
    _superx_turbo_mod.set_log_callbacks(_log_info, _log_error, _log_warning)
if _speaker_dsp_mod:
    _speaker_dsp_mod.set_log_callbacks(_log_info, _log_error, _log_warning)
if _oxpec_mod:
    _oxpec_mod.set_log_callbacks(_log_info, _log_error, _log_warning)
if _resume_fix_mod:
    _resume_fix_mod.set_log_callbacks(_log_info, _log_error, _log_warning)
if _sleep_fix_mod:
    _sleep_fix_mod.set_log_callbacks(_log_info, _log_error, _log_warning)
if _sleep_enable_mod:
    _sleep_enable_mod.set_log_callbacks(_log_info, _log_error, _log_warning)
if _xhci_recovery_mod:
    _xhci_recovery_mod.set_log_callbacks(_log_info, _log_error, _log_warning)


def _clean_env():
    """Strip Decky's LD_LIBRARY_PATH/LD_PRELOAD for subprocess calls."""
    env = os.environ.copy()
    for var in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
        env.pop(var, None)
    return env


def _restart_hhd():
    """Restart HHD so it re-detects hardware (e.g. after loading oxpec)."""
    _log_info("Restarting HHD to pick up new hardware...")
    try:
        r = subprocess.run(
            ["systemctl", "list-units", "--plain", "--no-legend", "--type=service", "hhd*"],
            capture_output=True, text=True, timeout=10, env=_clean_env()
        )
        units = []
        for line in r.stdout.strip().splitlines():
            parts = line.split()
            if parts:
                units.append(parts[0])
        if not units:
            units = ["hhd"]
        for unit in units:
            r = subprocess.run(
                ["systemctl", "restart", unit],
                capture_output=True, text=True, timeout=30, env=_clean_env()
            )
            if r.returncode == 0:
                _log_info(f"Restarted {unit}")
            else:
                _log_error(f"Failed to restart {unit}: {r.stderr.strip()}")
    except Exception as e:
        _log_error(f"HHD restart failed: {e}")


class Plugin:
    # Home button HID monitor instance
    home_monitor = None
    # Back paddle firmware remap monitor instance
    paddle_monitor = None
    # Super X Turbo button -> HHD overlay monitor instance
    turbo_monitor = None
    turbo_overlay_enabled = True
    tt_toggle_startup_enabled = True
    debug_logging_enabled = False

    def _load_settings(self):
        try:
            with open(SETTINGS_FILE) as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {}
        except Exception as e:
            _log_warning(f"Failed to load settings: {e}")
            data = {}
        self.turbo_overlay_enabled = bool(data.get("turbo_overlay_enabled", self.turbo_overlay_enabled))
        self.tt_toggle_startup_enabled = bool(data.get("tt_toggle_startup_enabled", self.tt_toggle_startup_enabled))
        self.debug_logging_enabled = bool(data.get("debug_logging_enabled", False))
        _set_helper_debug_logging(self.debug_logging_enabled)

    def _save_settings(self):
        data = {
            "turbo_overlay_enabled": self.turbo_overlay_enabled,
            "tt_toggle_startup_enabled": self.tt_toggle_startup_enabled,
            "debug_logging_enabled": self.debug_logging_enabled,
        }
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            with open(SETTINGS_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            _log_warning(f"Failed to save settings: {e}")

    def _get_dmi_info(self):
        if get_superx_dmi_info:
            return get_superx_dmi_info()
        return {"board_vendor": None, "board_name": None}

    def _is_superx(self):
        dmi = self._get_dmi_info()
        return (
            dmi.get("board_vendor") == "ONE-NETBOOK"
            and dmi.get("board_name") == "ONEXPLAYER SUPER X"
        )

    async def _main(self):
        """Plugin entry point — called by Decky on load."""
        try:
            from build_info import BUILD_ID
        except ImportError:
            BUILD_ID = "unknown"
        _log_info(f"ONEXPLAYER SUPER X Tools starting ({BUILD_ID})")
        _log_info(f"Plugin dir: {decky.DECKY_PLUGIN_DIR}")
        _log_info(f"Log dir: {decky.DECKY_PLUGIN_LOG_DIR}")
        self._load_settings()
        _log_info(f"Debug logging: {'enabled' if self.debug_logging_enabled else 'disabled'}")
        is_superx = self._is_superx()
        dmi = self._get_dmi_info()
        _log_info(
            "Detected DMI: "
            f"vendor={dmi.get('board_vendor') or 'unknown'}, "
            f"board={dmi.get('board_name') or 'unknown'}, "
            f"superx={is_superx}"
        )

        # Super X is a tablet and does not need the Apex HHD/controller patch
        # stack. Keep the existing Apex helpers active on non-Super-X devices.
        if not is_superx:
            if HomeButtonMonitor:
                self.home_monitor = HomeButtonMonitor()
            else:
                _log_warning("home_button module not available")
            if BackPaddleMonitor:
                self.paddle_monitor = BackPaddleMonitor()
            else:
                _log_warning("back_paddle module not available")

        hhd_restart_needed = False
        if not is_superx and xhci_check_and_recover:
            try:
                result = await asyncio.to_thread(xhci_check_and_recover)
                if result.get("needed") and result.get("success"):
                    _log_info("xHCI recovered — will restart HHD")
                    hhd_restart_needed = True
                elif result.get("needed") and not result.get("success"):
                    _log_error("xHCI recovery failed — gamepad may not work")
            except Exception as e:
                _log_error(f"xHCI recovery check failed: {e}")

        # Auto-load oxpec driver if not already loaded (survives reboots
        # even when hotfix overlay is lost since plugin runs on every boot)
        if ensure_oxpec_loaded:
            try:
                result = ensure_oxpec_loaded()
                if result.get("success") and result.get("loaded"):
                    method = result.get("method", "unknown")
                    _log_info(f"oxpec auto-loaded via {method}")
                    hhd_restart_needed = True
                elif result.get("already_loaded"):
                    _log_info("oxpec already loaded")
                else:
                    _log_warning(f"oxpec auto-load status: {result}")
            except Exception as e:
                _log_error(f"oxpec auto-load failed: {e}")

        if is_superx and self.tt_toggle_startup_enabled:
            self._enable_tt_toggle()

        if is_superx and self.turbo_overlay_enabled:
            self._start_turbo_monitor()

        if hhd_restart_needed:
            _log_info("Restarting HHD to pick up recovered hardware")
            _restart_hhd()

        if not is_superx and button_fix_status:
            status = button_fix_status()
            if status.get("applied"):
                _log_info("Button fix already applied — auto-starting monitors")
                self._start_home_monitor()
                self._start_paddle_monitor()

    async def _unload(self):
        """Plugin teardown — called by Decky on unload."""
        _log_info("ONEXPLAYER SUPER X Tools unloading")
        # Stop test sound if playing
        if stop_test_sound_impl:
            try:
                stop_test_sound_impl()
            except Exception:
                pass
        # Stop monitors if active
        if self.paddle_monitor:
            await self.paddle_monitor.stop()
        if self.home_monitor:
            await self.home_monitor.stop()
        if self.turbo_monitor:
            await self.turbo_monitor.stop()

    # -- Status overview --

    async def get_status(self):
        """Get combined status of all features — called by the frontend on load."""
        is_superx = self._is_superx()
        if is_superx:
            bf_status = {"applied": False, "error": "Disabled on Super X"}
        else:
            bf_status = button_fix_status() if button_fix_status else {"applied": False, "error": "module not loaded"}
        bf_status["home_monitor_running"] = self.home_monitor.is_running if self.home_monitor else False
        bf_status["paddle_monitor_running"] = self.paddle_monitor.is_running if self.paddle_monitor else False
        return {
            "button_fix": bf_status,
            "light_sleep": (
                {"applied": False, "has_problematic_kargs": False, "problematic_kargs": [], "light_sleep_present": [], "light_sleep_missing": []}
                if is_superx else
                (sleep_fix_status() if sleep_fix_status else {"applied": False, "has_problematic_kargs": False, "problematic_kargs": [], "light_sleep_present": [], "light_sleep_missing": []})
            ),
            "speaker_dsp": (
                {"enabled": False, "profile": None, "speaker_node": None}
                if is_superx else
                (speaker_dsp_status() if speaker_dsp_status else {"enabled": False, "profile": None, "speaker_node": None})
            ),
            "oxpec": oxpec_status() if oxpec_status else {"applied": False, "error": "module not loaded"},
            "resume_fix": (
                {"applied": False, "error": "Disabled on Super X"}
                if is_superx else
                (resume_fix_status() if resume_fix_status else {"applied": False, "error": "module not loaded"})
            ),
            "sleep_enable": (
                {"applied": False, "error": "Disabled on Super X"}
                if is_superx else
                (sleep_enable_status() if sleep_enable_status else {"applied": False, "error": "module not loaded"})
            ),
            "turbo_overlay": self._get_turbo_overlay_status(),
        }

    # -- Logs --

    async def get_logs(self, lines=20):
        """Return the last N lines from the log file."""
        try:
            with open(LOG_FILE) as f:
                all_lines = f.readlines()
            tail = [l.rstrip("\n") for l in all_lines[-lines:]]
            return {"lines": tail, "log_file": LOG_FILE}
        except Exception as e:
            return {"lines": [], "log_file": LOG_FILE, "error": str(e)}

    async def save_logs(self):
        """Copy the log file to the user's ~/Downloads/ with a timestamp."""
        import shutil
        from datetime import datetime
        try:
            user_home = _get_user_home()
            downloads = os.path.join(user_home, "Downloads")
            os.makedirs(downloads, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = os.path.join(downloads, f"oxp-superx-logs_{ts}.log")
            shutil.copy2(LOG_FILE, dest)
            _log_info(f"Logs saved to {dest}")
            return {"success": True, "path": dest}
        except Exception as e:
            _log_error(f"Failed to save logs: {e}")
            return {"success": False, "error": str(e)}

    # -- Button Fix --
    # Patches HHD (Handheld Daemon) to recognize Apex face buttons.
    # Requires ostree filesystem unlock since Bazzite is immutable.

    async def get_button_fix_status(self):
        if self._is_superx():
            return {"applied": False, "error": "Disabled on Super X"}
        if not button_fix_status:
            return {"applied": False, "error": "module not loaded"}
        return button_fix_status()

    async def apply_button_fix(self):
        if self._is_superx():
            return {
                "success": False,
                "error": "Apex HHD/controller fixes are disabled on Super X.",
            }
        if not apply_button_fix_impl:
            return {"success": False, "error": "button_fix module not loaded"}
        _log_info("Applying button fix...")
        try:
            result = await asyncio.to_thread(apply_button_fix_impl)
            if result.get("success"):
                _log_info(f"Button fix applied: {result.get('message', 'OK')}")
                self._start_home_monitor()
                self._start_paddle_monitor()
            else:
                _log_error(f"Button fix failed: {result.get('error', 'unknown')}")
            return result
        except Exception as e:
            _log_error(f"Button fix exception: {e}")
            return {"success": False, "error": str(e)}

    async def revert_button_fix(self):
        if self._is_superx():
            return {
                "success": True,
                "message": "Apex HHD/controller fixes are disabled on Super X.",
            }
        if not revert_button_fix_impl:
            return {"success": False, "error": "button_fix module not loaded"}
        _log_info("Reverting button fix...")
        try:
            await self._stop_paddle_monitor()
            await self._stop_home_monitor()
            result = await asyncio.to_thread(revert_button_fix_impl)
            if result.get("success"):
                _log_info(f"Button fix reverted: {result.get('message', 'OK')}")
            else:
                _log_error(f"Button fix revert failed: {result.get('error', 'unknown')}")
            return result
        except Exception as e:
            _log_error(f"Button fix revert exception: {e}")
            return {"success": False, "error": str(e)}

    # -- Light Sleep (s2idle kargs) --

    async def get_light_sleep_status(self):
        if not sleep_fix_status:
            return {"applied": False, "has_problematic_kargs": False, "problematic_kargs": [], "light_sleep_present": [], "light_sleep_missing": []}
        return sleep_fix_status()

    async def apply_light_sleep(self):
        if not apply_light_sleep_impl:
            return {"success": False, "error": "sleep_fix module not loaded"}
        _log_info("Applying light sleep kargs...")
        try:
            result = await asyncio.to_thread(apply_light_sleep_impl)
            if result.get("success"):
                _log_info(f"Light sleep applied: {result.get('message', 'OK')}")
            else:
                _log_error(f"Light sleep failed: {result.get('error', 'unknown')}")
            return result
        except Exception as e:
            _log_error(f"Light sleep exception: {e}")
            return {"success": False, "error": str(e)}

    async def revert_light_sleep(self):
        if not revert_light_sleep_impl:
            return {"success": False, "error": "sleep_fix module not loaded"}
        _log_info("Reverting light sleep kargs...")
        try:
            result = await asyncio.to_thread(revert_light_sleep_impl)
            if result.get("success"):
                _log_info(f"Light sleep reverted: {result.get('message', 'OK')}")
            else:
                _log_error(f"Light sleep revert failed: {result.get('error', 'unknown')}")
            return result
        except Exception as e:
            _log_error(f"Light sleep revert exception: {e}")
            return {"success": False, "error": str(e)}

    # Legacy compat — old frontend called remove_sleep_fix
    async def remove_sleep_fix(self):
        if not remove_sleep_fix_impl:
            return {"success": False, "error": "sleep_fix module not loaded"}
        try:
            return await asyncio.to_thread(remove_sleep_fix_impl)
        except Exception as e:
            return {"success": False, "error": str(e)}

    # -- Speaker DSP --

    async def get_speaker_dsp_status(self):
        if not speaker_dsp_status:
            return {"enabled": False, "profile": None, "speaker_node": None}
        return speaker_dsp_status()

    async def enable_speaker_dsp(self, profile="balanced"):
        if not enable_speaker_dsp_impl:
            return {"success": False, "error": "speaker_dsp module not loaded"}
        _log_info(f"Enabling speaker DSP ({profile})...")
        try:
            result = await asyncio.to_thread(enable_speaker_dsp_impl, profile)
            if result.get("success"):
                _log_info(f"Speaker DSP enabled: {result.get('message', 'OK')}")
            else:
                _log_error(f"Speaker DSP enable failed: {result.get('error', 'unknown')}")
            return result
        except Exception as e:
            _log_error(f"Speaker DSP enable exception: {e}")
            return {"success": False, "error": str(e)}

    async def disable_speaker_dsp(self):
        if not disable_speaker_dsp_impl:
            return {"success": False, "error": "speaker_dsp module not loaded"}
        _log_info("Disabling speaker DSP...")
        try:
            result = await asyncio.to_thread(disable_speaker_dsp_impl)
            if result.get("success"):
                _log_info(f"Speaker DSP disabled: {result.get('message', 'OK')}")
            else:
                _log_error(f"Speaker DSP disable failed: {result.get('error', 'unknown')}")
            return result
        except Exception as e:
            _log_error(f"Speaker DSP disable exception: {e}")
            return {"success": False, "error": str(e)}

    async def set_dsp_profile(self, profile):
        if not set_dsp_profile_impl:
            return {"success": False, "error": "speaker_dsp module not loaded"}
        _log_info(f"Switching speaker DSP profile to {profile}...")
        try:
            result = await asyncio.to_thread(set_dsp_profile_impl, profile)
            if result.get("success"):
                _log_info(f"Speaker DSP profile set: {result.get('message', 'OK')}")
            else:
                _log_error(f"Speaker DSP profile switch failed: {result.get('error', 'unknown')}")
            return result
        except Exception as e:
            _log_error(f"Speaker DSP profile exception: {e}")
            return {"success": False, "error": str(e)}

    async def list_dsp_profiles(self):
        if not list_dsp_profiles_impl:
            return {}
        return list_dsp_profiles_impl()

    async def get_preset_bands(self, profile_name):
        if not get_preset_bands_impl:
            return {"error": "speaker_dsp module not loaded"}
        return get_preset_bands_impl(profile_name)

    async def get_custom_profiles(self):
        if not get_custom_profiles_impl:
            return {"profiles": {}}
        return get_custom_profiles_impl()

    async def save_custom_profile(self, name, gains):
        if not save_custom_profile_impl:
            return {"success": False, "error": "speaker_dsp module not loaded"}
        _log_info(f"Saving custom EQ profile: {name}")
        try:
            result = await asyncio.to_thread(save_custom_profile_impl, name, gains)
            return result
        except Exception as e:
            _log_error(f"Save custom profile exception: {e}")
            return {"success": False, "error": str(e)}

    async def delete_custom_profile(self, name):
        if not delete_custom_profile_impl:
            return {"success": False, "error": "speaker_dsp module not loaded"}
        _log_info(f"Deleting custom EQ profile: {name}")
        try:
            result = await asyncio.to_thread(delete_custom_profile_impl, name)
            return result
        except Exception as e:
            _log_error(f"Delete custom profile exception: {e}")
            return {"success": False, "error": str(e)}

    async def play_test_sound(self):
        if not play_test_sound_impl:
            return {"success": False, "error": "speaker_dsp module not loaded"}
        try:
            return await asyncio.to_thread(play_test_sound_impl)
        except Exception as e:
            _log_error(f"Play test sound exception: {e}")
            return {"success": False, "error": str(e)}

    async def stop_test_sound(self):
        if not stop_test_sound_impl:
            return {"success": False, "error": "speaker_dsp module not loaded"}
        try:
            return await asyncio.to_thread(stop_test_sound_impl)
        except Exception as e:
            _log_error(f"Stop test sound exception: {e}")
            return {"success": False, "error": str(e)}

    async def bypass_speaker_dsp(self):
        if not bypass_speaker_dsp_impl:
            return {"success": False, "error": "speaker_dsp module not loaded"}
        try:
            return await asyncio.to_thread(bypass_speaker_dsp_impl)
        except Exception as e:
            _log_error(f"Bypass speaker DSP exception: {e}")
            return {"success": False, "error": str(e)}

    async def unbypass_speaker_dsp(self):
        if not unbypass_speaker_dsp_impl:
            return {"success": False, "error": "speaker_dsp module not loaded"}
        try:
            return await asyncio.to_thread(unbypass_speaker_dsp_impl)
        except Exception as e:
            _log_error(f"Unbypass speaker DSP exception: {e}")
            return {"success": False, "error": str(e)}

    async def is_bypassed_speaker_dsp(self):
        if not is_bypassed_speaker_dsp_impl:
            return {"bypassed": False, "error": "speaker_dsp module not loaded"}
        try:
            return await asyncio.to_thread(is_bypassed_speaker_dsp_impl)
        except Exception as e:
            _log_error(f"Is bypassed speaker DSP exception: {e}")
            return {"bypassed": False, "error": str(e)}

    # -- Home Button Monitor (private — managed by button fix lifecycle) --

    def _start_home_monitor(self):
        if not self.home_monitor:
            if HomeButtonMonitor:
                self.home_monitor = HomeButtonMonitor()
            else:
                _log_warning("Cannot start home monitor — module not loaded")
                return
        if not self.home_monitor.is_running:
            loop = asyncio.get_event_loop()
            self.home_monitor.start(loop)
            _log_info("Home button monitor started")

    async def _stop_home_monitor(self):
        if self.home_monitor and self.home_monitor.is_running:
            await self.home_monitor.stop()
            _log_info("Home button monitor stopped")

    # -- Back Paddle Monitor (private — managed by button fix lifecycle) --

    def _start_paddle_monitor(self):
        if not self.paddle_monitor:
            if BackPaddleMonitor:
                self.paddle_monitor = BackPaddleMonitor()
            else:
                _log_warning("Cannot start paddle monitor — module not loaded")
                return
        if not self.paddle_monitor.is_running:
            loop = asyncio.get_event_loop()
            self.paddle_monitor.start(loop)
            _log_info("Back paddle monitor started (firmware remap mode)")

    async def _stop_paddle_monitor(self):
        if self.paddle_monitor and self.paddle_monitor.is_running:
            await self.paddle_monitor.stop()
            _log_info("Back paddle monitor stopped")

    # -- Super X Turbo Overlay Monitor --

    def _get_turbo_overlay_status(self):
        dmi = get_superx_dmi_info() if get_superx_dmi_info else {}
        tt_paths = find_tt_toggle_paths() if find_tt_toggle_paths else []
        monitor_status = self.turbo_monitor.status() if self.turbo_monitor and hasattr(self.turbo_monitor, "status") else {}
        return {
            "enabled": self.turbo_overlay_enabled,
            "running": bool(monitor_status.get("running", self.turbo_monitor.is_running if self.turbo_monitor else False)),
            "watched_device_count": int(monitor_status.get("watched_device_count", 0) or 0),
            "task_id": monitor_status.get("task_id"),
            "debug_logging_enabled": self.debug_logging_enabled,
            "tt_toggle_startup_enabled": self.tt_toggle_startup_enabled,
            "tt_toggle_paths": tt_paths,
            "is_superx": (
                dmi.get("board_vendor") == "ONE-NETBOOK"
                and dmi.get("board_name") == "ONEXPLAYER SUPER X"
            ),
            "board_vendor": dmi.get("board_vendor"),
            "board_name": dmi.get("board_name"),
        }

    def _enable_tt_toggle(self):
        if not enable_tt_toggle_impl:
            _log_warning("Cannot enable tt_toggle — superx_turbo module not loaded")
            return {"success": False, "error": "superx_turbo module not loaded"}
        if is_superx_device and not is_superx_device():
            _log_warning("Skipping tt_toggle because DMI does not match ONEXPLAYER SUPER X")
            return {"success": False, "error": "not ONEXPLAYER SUPER X"}
        return enable_tt_toggle_impl()

    def _start_turbo_monitor(self):
        if is_superx_device and not is_superx_device():
            _log_warning("Not starting Turbo watcher because DMI does not match ONEXPLAYER SUPER X")
            return {"success": False, "error": "not ONEXPLAYER SUPER X"}
        tt_result = self._enable_tt_toggle()
        if not tt_result.get("success"):
            _log_warning(
                "Not starting Turbo watcher because tt_toggle is not ready: "
                f"{tt_result.get('error', 'unknown')}"
            )
            return tt_result
        if not self.turbo_monitor:
            if SuperXTurboMonitor:
                self.turbo_monitor = SuperXTurboMonitor()
            else:
                _log_warning("Cannot start Turbo watcher — module not loaded")
                return {"success": False, "error": "superx_turbo module not loaded"}
        if self.turbo_monitor.is_running:
            return {"success": True, "message": "Turbo overlay watcher already running"}
        if not self.turbo_monitor.is_running:
            loop = asyncio.get_event_loop()
            started = self.turbo_monitor.start(loop)
            if started:
                _log_info("Super X Turbo overlay watcher started")
        return {"success": True, "message": "Turbo overlay watcher enabled"}

    async def _stop_turbo_monitor(self):
        if self.turbo_monitor and self.turbo_monitor.is_running:
            await self.turbo_monitor.stop()
            _log_info("Super X Turbo overlay watcher stopped")

    async def get_turbo_overlay_status(self):
        return self._get_turbo_overlay_status()

    async def set_turbo_overlay_enabled(self, enabled: bool):
        self.turbo_overlay_enabled = bool(enabled)
        if self.turbo_overlay_enabled:
            result = self._start_turbo_monitor()
            if result and not result.get("success"):
                self.turbo_overlay_enabled = False
                self._save_settings()
                return result
            self._save_settings()
            return result or {"success": True, "message": "Turbo overlay watcher enabled"}
        await self._stop_turbo_monitor()
        self._save_settings()
        return {"success": True, "message": "Turbo overlay watcher disabled"}

    async def set_tt_toggle_startup_enabled(self, enabled: bool):
        self.tt_toggle_startup_enabled = bool(enabled)
        if self.tt_toggle_startup_enabled:
            result = await asyncio.to_thread(self._enable_tt_toggle)
            self._save_settings()
            if result.get("success"):
                return {"success": True, "message": "tt_toggle enabled"}
            return {
                "success": True,
                "warning": result.get("error", "tt_toggle not available"),
                "message": "tt_toggle will be enabled on startup when available",
            }
        self._save_settings()
        return {"success": True, "message": "tt_toggle startup enable disabled"}

    async def set_debug_logging_enabled(self, enabled: bool):
        self.debug_logging_enabled = bool(enabled)
        _set_helper_debug_logging(self.debug_logging_enabled)
        self._save_settings()
        _log_info(f"Debug logging {'enabled' if self.debug_logging_enabled else 'disabled'}")
        return {"success": True, "message": f"Debug logging {'enabled' if self.debug_logging_enabled else 'disabled'}"}

    # -- oxpec EC Sensor Driver --

    async def get_oxpec_status(self):
        if not oxpec_status:
            return {"applied": False, "error": "module not loaded"}
        return oxpec_status()

    async def apply_oxpec(self):
        if not apply_oxpec_impl:
            return {"success": False, "error": "oxpec_loader module not loaded"}
        _log_info("Installing oxpec driver...")
        try:
            await self._stop_turbo_monitor()
            result = await asyncio.to_thread(apply_oxpec_impl)
            if result.get("success"):
                _log_info(f"oxpec applied: {result.get('message', 'OK')}")
                if self.tt_toggle_startup_enabled:
                    await asyncio.to_thread(self._enable_tt_toggle)
                # Restart HHD so it detects the new hwmon for fan control
                await asyncio.to_thread(_restart_hhd)
                if self.turbo_overlay_enabled:
                    self._start_turbo_monitor()
            else:
                _log_error(f"oxpec failed: {result.get('error', 'unknown')}")
            return result
        except Exception as e:
            _log_error(f"oxpec exception: {e}")
            return {"success": False, "error": str(e)}

    async def rebuild_oxpec(self):
        if not rebuild_oxpec_impl:
            return {"success": False, "error": "oxpec_loader module not loaded"}
        _log_info("Rebuilding oxpec driver for current kernel...")
        try:
            await self._stop_turbo_monitor()
            result = await asyncio.to_thread(rebuild_oxpec_impl)
            if result.get("success"):
                _log_info(f"oxpec rebuilt: {result.get('message', 'OK')}")
                if self.tt_toggle_startup_enabled:
                    await asyncio.to_thread(self._enable_tt_toggle)
                await asyncio.to_thread(_restart_hhd)
                if self.turbo_overlay_enabled:
                    self._start_turbo_monitor()
            else:
                _log_error(f"oxpec rebuild failed: {result.get('error', 'unknown')}")
            return result
        except Exception as e:
            _log_error(f"oxpec rebuild exception: {e}")
            return {"success": False, "error": str(e)}

    async def revert_oxpec(self):
        if not revert_oxpec_impl:
            return {"success": False, "error": "oxpec_loader module not loaded"}
        _log_info("Removing oxpec driver...")
        try:
            await self._stop_turbo_monitor()
            result = await asyncio.to_thread(revert_oxpec_impl)
            if result.get("success"):
                _log_info(f"oxpec reverted: {result.get('message', 'OK')}")
            else:
                _log_error(f"oxpec revert failed: {result.get('error', 'unknown')}")
            return result
        except Exception as e:
            _log_error(f"oxpec revert exception: {e}")
            return {"success": False, "error": str(e)}

    # -- Resume Recovery --

    async def get_resume_fix_status(self):
        if not resume_fix_status:
            return {"applied": False, "error": "module not loaded"}
        return resume_fix_status()

    async def apply_resume_fix(self):
        if not apply_resume_fix_impl:
            return {"success": False, "error": "resume_fix module not loaded"}
        _log_info("Installing resume recovery fix...")
        try:
            result = await asyncio.to_thread(apply_resume_fix_impl)
            if result.get("success"):
                _log_info(f"Resume fix applied: {result.get('message', 'OK')}")
            else:
                _log_error(f"Resume fix failed: {result.get('error', 'unknown')}")
            return result
        except Exception as e:
            _log_error(f"Resume fix exception: {e}")
            return {"success": False, "error": str(e)}

    async def revert_resume_fix(self):
        if not revert_resume_fix_impl:
            return {"success": False, "error": "resume_fix module not loaded"}
        _log_info("Removing resume recovery fix...")
        try:
            result = await asyncio.to_thread(revert_resume_fix_impl)
            if result.get("success"):
                _log_info(f"Resume fix reverted: {result.get('message', 'OK')}")
            else:
                _log_error(f"Resume fix revert failed: {result.get('error', 'unknown')}")
            return result
        except Exception as e:
            _log_error(f"Resume fix revert exception: {e}")
            return {"success": False, "error": str(e)}

    # -- xHCI Recovery (manual trigger) --

    async def recover_gamepad(self):
        """Manually trigger xHCI rebind + HHD restart to recover the gamepad."""
        if not xhci_check_and_recover:
            return {"success": False, "error": "xhci_recovery module not loaded"}
        _log_info("Manual gamepad recovery triggered")
        try:
            result = await asyncio.to_thread(xhci_check_and_recover)
            if result.get("already_ok"):
                return {"success": True, "message": "Gamepad already connected"}
            if result.get("success"):
                _log_info("xHCI recovered — restarting HHD")
                _restart_hhd()
                return {"success": True, "message": "Gamepad recovered and HHD restarted"}
            return {"success": False, "error": "Recovery failed — gamepad not detected after rebind"}
        except Exception as e:
            _log_error(f"Gamepad recovery exception: {e}")
            return {"success": False, "error": str(e)}

    # -- Sleep Enable --

    async def get_sleep_enable_status(self):
        if not sleep_enable_status:
            return {"applied": False, "error": "module not loaded"}
        return sleep_enable_status()

    async def apply_sleep_enable(self):
        if not apply_sleep_enable_impl:
            return {"success": False, "error": "sleep_enable module not loaded"}
        _log_info("Applying sleep enablement fix...")
        try:
            result = await asyncio.to_thread(apply_sleep_enable_impl)
            if result.get("success"):
                _log_info(f"Sleep enable applied: {result.get('message', 'OK')}")
            else:
                _log_error(f"Sleep enable failed: {result.get('error', 'unknown')}")
            return result
        except Exception as e:
            _log_error(f"Sleep enable exception: {e}")
            return {"success": False, "error": str(e)}

    async def revert_sleep_enable(self):
        if not revert_sleep_enable_impl:
            return {"success": False, "error": "sleep_enable module not loaded"}
        _log_info("Reverting sleep enablement fix...")
        try:
            result = await asyncio.to_thread(revert_sleep_enable_impl)
            if result.get("success"):
                _log_info(f"Sleep enable reverted: {result.get('message', 'OK')}")
            else:
                _log_error(f"Sleep enable revert failed: {result.get('error', 'unknown')}")
            return result
        except Exception as e:
            _log_error(f"Sleep enable revert exception: {e}")
            return {"success": False, "error": str(e)}
