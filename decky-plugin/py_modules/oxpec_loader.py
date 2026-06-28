"""EC platform driver (oxpec) loader for ONEXPLAYER SUPER X.

Installs and loads the oxpec kernel module which provides hwmon sensors
and enables HHD native fan curves. Bundled .ko files are organized per
kernel version in py_modules/oxpec/<kernel>/oxpec.ko.

Loading strategy:
  1. modprobe oxpec  (works when upstream kernel ships APEX DMI entry)
  2. insmod with bundled .ko matching the running kernel
  3. insmod from /var/lib/oxpec/oxpec.ko (previously installed copy)
"""

import logging
import os
import subprocess
import glob
import time
import shutil

logger = logging.getLogger("OXP-OxpecLoader")

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


def _clean_env():
    env = os.environ.copy()
    for var in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
        env.pop(var, None)
    return env


# Paths
_PLUGIN_DIR = os.path.dirname(os.path.dirname(__file__))
_OXPEC_DIR = os.path.join(os.path.dirname(__file__), "oxpec")
_OXPEC_BUILD_DIR = os.path.join(_OXPEC_DIR, "build")
_INSTALL_DIR = "/var/lib/oxpec"
_INSTALL_KO = os.path.join(_INSTALL_DIR, "oxpec.ko")
_SERVICE_NAME = "oxpec-load.service"
_SERVICE_PATH = f"/etc/systemd/system/{_SERVICE_NAME}"
_OXP_PLATFORM_DIR = "/sys/devices/platform/oxp-platform"
_TT_TOGGLE_EXACT_PATH = os.path.join(_OXP_PLATFORM_DIR, "tt_toggle")
_PLATFORM_FAN_GLOB = os.path.join(_OXP_PLATFORM_DIR, "hwmon", "hwmon*", "fan1_input")
_SYSFS_RETRY_SECS = 5.0
_SYSFS_RETRY_INTERVAL_SECS = 0.25


def _make_service_content(ko_path):
    """Generate systemd service content with modprobe-first, insmod fallback."""
    return f"""[Unit]
Description=Load oxpec EC platform driver for OneXPlayer
DefaultDependencies=no
After=systemd-modules-load.service
Before=hhd@.service hhd.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'modprobe oxpec 2>/dev/null || insmod {ko_path}'
ExecStop=/sbin/rmmod oxpec

[Install]
WantedBy=multi-user.target
"""


def _find_bundled_ko(kernel=None):
    """Find bundled oxpec.ko matching a kernel version.

    Returns (ko_path, kernel_version) or (None, None).
    """
    if kernel is None:
        kernel = _get_running_kernel()
    if not kernel:
        return None, None
    ko = os.path.join(_OXPEC_DIR, kernel, "oxpec.ko")
    return (ko, kernel) if os.path.exists(ko) else (None, None)


def _get_module_vermagic(ko_path):
    if not ko_path or not os.path.exists(ko_path):
        return None
    try:
        r = subprocess.run(
            ["modinfo", "-F", "vermagic", ko_path],
            capture_output=True, text=True, timeout=10, env=_clean_env()
        )
        if r.returncode != 0:
            _log_warning(f"modinfo vermagic failed for {ko_path}: {r.stderr.strip()}")
            return None
        return r.stdout.strip()
    except Exception as e:
        _log_warning(f"modinfo vermagic exception for {ko_path}: {e}")
        return None


def _vermagic_kernel(vermagic):
    if not vermagic:
        return None
    parts = vermagic.split()
    return parts[0] if parts else None


def _ko_has_superx_dmi(ko_path):
    if not ko_path or not os.path.exists(ko_path):
        return False
    try:
        with open(ko_path, "rb") as f:
            return b"ONEXPLAYER SUPER X" in f.read()
    except OSError:
        return False


def _ko_matches_kernel(ko_path, kernel=None):
    if kernel is None:
        kernel = _get_running_kernel()
    vermagic = _get_module_vermagic(ko_path)
    return (
        bool(kernel and vermagic and _vermagic_kernel(vermagic) == kernel and _ko_has_superx_dmi(ko_path)),
        vermagic,
    )


def _find_any_bundled_ko():
    for kernel in reversed(_list_bundled_kernels()):
        ko = os.path.join(_OXPEC_DIR, kernel, "oxpec.ko")
        if os.path.exists(ko):
            return ko, kernel
    return None, None


def _list_bundled_kernels():
    """List kernel versions with bundled .ko files."""
    if not os.path.isdir(_OXPEC_DIR):
        return []
    return sorted(
        d for d in os.listdir(_OXPEC_DIR)
        if os.path.isfile(os.path.join(_OXPEC_DIR, d, "oxpec.ko"))
    )


def _safe_exists(path):
    return bool(path) and os.path.exists(path)


def _safe_is_file(path):
    return bool(path) and os.path.isfile(path)


def _safe_is_dir(path):
    return bool(path) and os.path.isdir(path)


def _glob_paths(pattern):
    if not pattern:
        return []
    return glob.glob(pattern)


def _find_platform_fan_nodes():
    return sorted(p for p in _glob_paths(_PLATFORM_FAN_GLOB) if _safe_is_file(p))


def _find_hwmon():
    """Find the oxpec hwmon device path, if loaded."""
    fan_nodes = _find_platform_fan_nodes()
    if fan_nodes:
        return os.path.dirname(fan_nodes[0])

    hwmon_base = "/sys/class/hwmon"
    if not _safe_is_dir(hwmon_base):
        return None
    for entry in os.listdir(hwmon_base):
        name_path = os.path.join(hwmon_base, entry, "name")
        try:
            with open(name_path) as f:
                if f.read().strip() == "oxpec":
                    return os.path.join(hwmon_base, entry)
        except (OSError, IOError):
            continue
    return None


def _existing_paths(paths):
    """Return paths that currently exist."""
    return [p for p in paths if _safe_exists(p)]


def _find_tt_toggle_paths():
    paths = []
    if _safe_is_file(_TT_TOGGLE_EXACT_PATH):
        paths.append(_TT_TOGGLE_EXACT_PATH)

    if _safe_is_dir(_OXP_PLATFORM_DIR):
        for root, _, files in os.walk(_OXP_PLATFORM_DIR):
            if "tt_toggle" not in files:
                continue
            path = os.path.join(root, "tt_toggle")
            if path not in paths:
                paths.append(path)
    return paths


def _wait_for_sysfs_nodes(timeout_secs=_SYSFS_RETRY_SECS):
    deadline = time.monotonic() + timeout_secs
    while True:
        nodes = _find_sysfs_nodes()
        if nodes["turbo_toggle_nodes"] or nodes["fan_control_nodes"]:
            return nodes
        if time.monotonic() >= deadline:
            return nodes
        time.sleep(_SYSFS_RETRY_INTERVAL_SECS)


def _log_sysfs_nodes(nodes=None):
    if nodes is None:
        nodes = _find_sysfs_nodes()

    if _safe_is_dir(_OXP_PLATFORM_DIR):
        _log_info(f"oxp-platform found: {_OXP_PLATFORM_DIR}")
    else:
        _log_warning(f"oxp-platform missing: {_OXP_PLATFORM_DIR}")

    if nodes.get("turbo_toggle_nodes"):
        _log_info(f"tt_toggle found: {', '.join(nodes['turbo_toggle_nodes'])}")
    else:
        _log_warning("tt_toggle not detected")

    fan_nodes = [p for p in nodes.get("fan_control_nodes", []) if p.endswith("fan1_input")]
    if fan_nodes:
        _log_info(f"fan1_input found: {', '.join(fan_nodes)}")
    else:
        _log_warning(f"fan1_input not detected under {_PLATFORM_FAN_GLOB}")


def _find_sysfs_nodes():
    """Find fan, charge, and turbo-takeover nodes exposed by oxpec."""
    hwmon_path = _find_hwmon()
    fan_nodes = _find_platform_fan_nodes()
    turbo_nodes = _find_tt_toggle_paths()
    if hwmon_path:
        for path in _existing_paths([
            os.path.join(hwmon_path, "fan1_input"),
            os.path.join(hwmon_path, "pwm1"),
            os.path.join(hwmon_path, "pwm1_enable"),
        ]):
            if path not in fan_nodes:
                fan_nodes.append(path)

    charge_nodes = []
    power_supply_base = "/sys/class/power_supply"
    if _safe_is_dir(power_supply_base):
        for entry in sorted(os.listdir(power_supply_base)):
            base = os.path.join(power_supply_base, entry)
            charge_nodes.extend(_existing_paths([
                os.path.join(base, "charge_control_end_threshold"),
                os.path.join(base, "charge_behaviour"),
            ]))

    return {
        "fan_control_nodes": fan_nodes,
        "charge_control_nodes": charge_nodes,
        "turbo_toggle_nodes": turbo_nodes,
    }


def _is_module_loaded():
    """Check if oxpec module is currently loaded."""
    try:
        with open("/proc/modules") as f:
            for line in f:
                if line.startswith("oxpec "):
                    return True
    except OSError:
        pass
    return False


def _get_running_kernel():
    """Get the running kernel version."""
    try:
        r = subprocess.run(["uname", "-r"], capture_output=True, text=True, timeout=5, env=_clean_env())
        return r.stdout.strip()
    except Exception:
        return None


def _try_modprobe():
    """Try modprobe oxpec. Returns {"success": bool, "error": str}."""
    try:
        r = subprocess.run(
            ["modprobe", "oxpec"],
            capture_output=True, text=True, timeout=10, env=_clean_env()
        )
        if r.returncode == 0:
            return {"success": True}
        return {"success": False, "error": r.stderr.strip()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _try_insmod(ko_path):
    """Try insmod with specific .ko. Returns {"success": bool, "error": str}."""
    try:
        r = subprocess.run(
            ["insmod", ko_path],
            capture_output=True, text=True, timeout=10, env=_clean_env()
        )
        if r.returncode == 0:
            return {"success": True}
        return {"success": False, "error": r.stderr.strip()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _preflight_rebuild(kernel):
    build_dir = f"/lib/modules/{kernel}/build" if kernel else None
    errors = []
    if not kernel:
        errors.append("Cannot determine running kernel")
    if not _safe_is_dir(build_dir):
        errors.append(f"Kernel build directory missing: {build_dir}")
    if not _safe_is_dir(_OXPEC_BUILD_DIR):
        errors.append(f"oxpec build source directory missing: {_OXPEC_BUILD_DIR}")
    if not shutil.which("make"):
        errors.append("make not found")
    if not (shutil.which("gcc") or shutil.which("cc")):
        errors.append("gcc/cc not found")
    return errors, build_dir


def rebuild_for_current_kernel():
    """Rebuild bundled oxpec.ko for the running kernel, then load it."""
    kernel = _get_running_kernel()
    errors, kernel_build_dir = _preflight_rebuild(kernel)
    if errors:
        message = "Cannot rebuild oxpec.ko: " + "; ".join(errors)
        _log_error(message)
        return {"success": False, "error": message, "steps": errors}

    steps = [f"Running kernel: {kernel}", f"Kernel build directory: {kernel_build_dir}"]
    clean_cmd = ["make", "-C", kernel_build_dir, f"M={_OXPEC_BUILD_DIR}", "clean"]
    build_cmd = ["make", "-C", kernel_build_dir, f"M={_OXPEC_BUILD_DIR}", "modules"]
    _log_info(f"Rebuilding oxpec.ko: {' '.join(build_cmd)}")

    try:
        clean = subprocess.run(clean_cmd, capture_output=True, text=True, timeout=60, env=_clean_env())
        if clean.stdout.strip():
            _log_info(f"oxpec rebuild clean stdout:\n{clean.stdout.strip()[-2000:]}")
        if clean.stderr.strip():
            _log_warning(f"oxpec rebuild clean stderr:\n{clean.stderr.strip()[-2000:]}")
        r = subprocess.run(build_cmd, capture_output=True, text=True, timeout=180, env=_clean_env())
    except Exception as e:
        message = f"Rebuild failed to start: {e}"
        _log_error(message)
        return {"success": False, "error": message, "steps": steps}

    stdout = r.stdout.strip()
    stderr = r.stderr.strip()
    if stdout:
        _log_info(f"oxpec rebuild stdout:\n{stdout[-4000:]}")
    if stderr:
        _log_warning(f"oxpec rebuild stderr:\n{stderr[-4000:]}")

    steps.append("make completed" if r.returncode == 0 else f"make failed: {r.returncode}")
    if r.returncode != 0:
        return {
            "success": False,
            "error": f"oxpec rebuild failed with exit code {r.returncode}",
            "steps": steps,
            "stdout": stdout[-4000:],
            "stderr": stderr[-4000:],
        }

    built_ko = os.path.join(_OXPEC_BUILD_DIR, "oxpec.ko")
    matches, vermagic = _ko_matches_kernel(built_ko, kernel)
    _log_info(f"rebuilt oxpec.ko vermagic: {vermagic or 'unknown'}")
    if not matches:
        return {
            "success": False,
            "error": (
                "Rebuilt oxpec.ko vermagic does not match running kernel. "
                f"kernel={kernel}, vermagic={vermagic or 'unknown'}"
            ),
            "steps": steps,
            "stdout": stdout[-4000:],
            "stderr": stderr[-4000:],
        }

    target_dir = os.path.join(_OXPEC_DIR, kernel)
    target_ko = os.path.join(target_dir, "oxpec.ko")
    try:
        os.makedirs(target_dir, exist_ok=True)
        shutil.copy2(built_ko, target_ko)
    except Exception as e:
        return {"success": False, "error": f"Failed to install rebuilt oxpec.ko: {e}", "steps": steps}

    steps.append(f"Installed rebuilt module: {target_ko}")
    _log_info(f"Installed rebuilt oxpec.ko: {target_ko}")

    if _is_module_loaded():
        revert()
    load_result = apply()
    steps.extend(load_result.get("steps", []))
    if load_result.get("success"):
        return {
            "success": True,
            "message": "Rebuilt and loaded oxpec.ko",
            "steps": steps,
            "stdout": stdout[-4000:],
            "stderr": stderr[-4000:],
        }
    return {
        "success": False,
        "error": load_result.get("error", "Rebuilt module but failed to load oxpec"),
        "steps": steps,
        "stdout": stdout[-4000:],
        "stderr": stderr[-4000:],
    }


def is_applied():
    """Check current status of oxpec driver installation."""
    kernel = _get_running_kernel()
    bundled_kernels = _list_bundled_kernels()
    bundled_ko, _ = _find_bundled_ko(kernel)
    mismatch_ko = None
    mismatch_kernel = None
    if not bundled_ko:
        mismatch_ko, mismatch_kernel = _find_any_bundled_ko()
    bundled_matches = False
    bundled_vermagic = None
    if bundled_ko:
        bundled_matches, bundled_vermagic = _ko_matches_kernel(bundled_ko, kernel)
    mismatch_vermagic = _get_module_vermagic(mismatch_ko) if mismatch_ko else None

    module_loaded = _is_module_loaded()
    hwmon_path = _find_hwmon()
    sysfs_nodes = _find_sysfs_nodes()

    # Determine load method if loaded
    load_method = None
    if module_loaded:
        # Check if kernel has oxpec in its module tree (would mean modprobe works)
        try:
            r = subprocess.run(
                ["modprobe", "--dry-run", "oxpec"],
                capture_output=True, text=True, timeout=5, env=_clean_env()
            )
            load_method = "modprobe" if r.returncode == 0 else "insmod"
        except Exception:
            load_method = "insmod"

    # kernel_compatible: True if loaded, exact bundled .ko exists and matches, or modprobe works.
    kernel_compatible = module_loaded or bundled_matches
    if not kernel_compatible:
        try:
            r = subprocess.run(
                ["modprobe", "--dry-run", "oxpec"],
                capture_output=True, text=True, timeout=5, env=_clean_env()
            )
            if r.returncode == 0:
                kernel_compatible = True
        except Exception:
            pass

    service_enabled = False
    service_exists = os.path.exists(_SERVICE_PATH)
    if service_exists:
        try:
            r = subprocess.run(
                ["systemctl", "is-enabled", _SERVICE_NAME],
                capture_output=True, text=True, timeout=10, env=_clean_env()
            )
            service_enabled = r.stdout.strip() == "enabled"
        except Exception:
            pass

    applied = module_loaded and service_enabled

    return {
        "applied": applied,
        "module_loaded": module_loaded,
        "service_enabled": service_enabled,
        "hwmon_path": hwmon_path,
        "kernel_compatible": kernel_compatible,
        "kernel_mismatch": bool(not kernel_compatible),
        "kernel_mismatch_message": (
            None if kernel_compatible else "Kernel mismatch. Rebuild oxpec.ko for current kernel."
        ),
        "running_kernel": kernel,
        "bundled_kernels": bundled_kernels,
        "bundled_ko_path": bundled_ko,
        "bundled_vermagic": bundled_vermagic,
        "mismatch_ko_path": mismatch_ko,
        "mismatch_bundled_kernel": mismatch_kernel,
        "mismatch_vermagic": mismatch_vermagic,
        "load_method": load_method,
        **sysfs_nodes,
    }


def _install_bundled_ko(bundled_ko):
    """Copy bundled .ko to /var/lib/oxpec/ with SELinux context.

    Returns (success, error_msg).
    """
    import shutil
    try:
        os.makedirs(_INSTALL_DIR, exist_ok=True)
        shutil.copy2(bundled_ko, _INSTALL_KO)
    except Exception as e:
        return False, f"Failed to copy oxpec.ko: {e}"
    try:
        subprocess.run(
            ["chcon", "-t", "modules_object_t", _INSTALL_KO],
            capture_output=True, text=True, timeout=10, env=_clean_env()
        )
    except Exception:
        pass  # SELinux may not be enforcing
    return True, None


def ensure_loaded():
    """Load the oxpec module if not already loaded.

    Lightweight startup check — tries modprobe first (future-proof),
    falls back to kernel-matched bundled .ko, then /var/lib/oxpec copy.
    """
    if _is_module_loaded():
        return {"success": True, "already_loaded": True}

    kernel = _get_running_kernel()

    # 1. Try modprobe (works when upstream kernel ships APEX DMI entry)
    result = _try_modprobe()
    if result["success"] and _is_module_loaded():
        _log_info("oxpec loaded via modprobe")
        return {"success": True, "loaded": True, "method": "modprobe"}

    modprobe_error = result.get("error", "unknown")

    # 2. Try bundled .ko for running kernel
    bundled_ko, matched_kernel = _find_bundled_ko(kernel)
    if bundled_ko:
        matches, vermagic = _ko_matches_kernel(bundled_ko, kernel)
        if not matches:
            msg = (
                "Kernel mismatch. Rebuild oxpec.ko for current kernel. "
                f"kernel={kernel}, vermagic={vermagic or 'unknown'}"
            )
            _log_warning(msg)
            return {"success": False, "error": msg, "kernel_mismatch": True}
        _log_info(f"Trying bundled oxpec.ko for {matched_kernel}")
        result = _try_insmod(bundled_ko)
        if result["success"] and _is_module_loaded():
            _log_info(f"oxpec loaded via insmod (bundled, {matched_kernel})")
            return {"success": True, "loaded": True, "method": "insmod"}

        insmod_error = result.get("error", "")
        _log_warning(f"Bundled insmod failed: {insmod_error}")

        # Permission denied → copy to /var/lib/oxpec with SELinux context and retry
        if "Permission denied" in insmod_error or "Operation not permitted" in insmod_error:
            _log_info("Copying bundled .ko to /var/lib/oxpec for SELinux compatibility")
            ok, err = _install_bundled_ko(bundled_ko)
            if ok:
                result = _try_insmod(_INSTALL_KO)
                if result["success"] and _is_module_loaded():
                    _log_info(f"oxpec loaded via insmod (/var/lib/oxpec, copied from bundled {matched_kernel})")
                    return {"success": True, "loaded": True, "method": "insmod"}
                _log_warning(f"Installed insmod also failed: {result.get('error', 'unknown')}")
            else:
                _log_warning(f"Copy failed: {err}")

    # 3. Try installed copy as last resort
    if os.path.exists(_INSTALL_KO):
        _log_info(f"Trying installed oxpec.ko from {_INSTALL_KO}")
        result = _try_insmod(_INSTALL_KO)
        if result["success"] and _is_module_loaded():
            _log_info("oxpec loaded via insmod (/var/lib/oxpec)")
            return {"success": True, "loaded": True, "method": "insmod"}

    # All methods failed
    bundled_kernels = _list_bundled_kernels()
    error_msg = (
        f"Failed to load oxpec. "
        f"modprobe: {modprobe_error}. "
        f"Running kernel: {kernel}. "
        f"Bundled .ko available for: {', '.join(bundled_kernels) if bundled_kernels else 'none'}"
    )
    _log_error(error_msg)
    return {"success": False, "error": error_msg}


def apply():
    """Install and load the oxpec kernel module."""
    steps = []
    _log_info("=== oxpec Apply Start ===")

    # Check if already applied
    status = is_applied()
    if status.get("applied"):
        return {"success": True, "message": "Already applied", "steps": ["Already applied"]}

    kernel = _get_running_kernel()

    # Try actual modprobe first (not just --dry-run, which only checks file exists)
    modprobe_works = False
    result = _try_modprobe()
    if result["success"] and _is_module_loaded():
        _log_info("oxpec loaded via modprobe")
        modprobe_works = True
        steps.append("Loaded via modprobe")
        ko_for_service = None  # service will just use modprobe
    else:
        modprobe_err = result.get("error", "unknown")
        _log_info(f"modprobe failed: {modprobe_err} — trying bundled .ko")

        # Find matching bundled .ko
        bundled_ko, matched_kernel = _find_bundled_ko(kernel)
        if not bundled_ko:
            bundled_kernels = _list_bundled_kernels()
            return {
                "success": False,
                "error": (
                    f"No oxpec.ko for kernel {kernel}. "
                    f"Available: {', '.join(bundled_kernels) if bundled_kernels else 'none'}. "
                    f"Update the plugin for new kernel support."
                ),
                "steps": steps,
            }

        steps.append(f"Using bundled .ko for {matched_kernel}")
        matches, vermagic = _ko_matches_kernel(bundled_ko, kernel)
        if not matches:
            msg = (
                "Kernel mismatch. Rebuild oxpec.ko for current kernel. "
                f"kernel={kernel}, vermagic={vermagic or 'unknown'}"
            )
            _log_warning(msg)
            return {"success": False, "error": msg, "steps": steps, "kernel_mismatch": True}

        # Copy .ko to install location with SELinux context
        ok, err = _install_bundled_ko(bundled_ko)
        if not ok:
            return {"success": False, "error": err, "steps": steps}
        _log_info(f"Copied oxpec.ko to {_INSTALL_KO}")
        steps.append(f"Copied oxpec.ko to {_INSTALL_DIR}")
        steps.append("Set SELinux context")

        ko_for_service = _INSTALL_KO

    # Write systemd service (modprobe-first, insmod fallback)
    try:
        service_content = _make_service_content(ko_for_service or _INSTALL_KO)
        with open(_SERVICE_PATH, "w") as f:
            f.write(service_content)
        _log_info(f"Created {_SERVICE_PATH}")
        steps.append("Created systemd service")
    except Exception as e:
        return {"success": False, "error": f"Failed to write service file: {e}", "steps": steps}

    # Reload systemd and enable+start
    try:
        subprocess.run(
            ["systemctl", "daemon-reload"],
            capture_output=True, text=True, timeout=30, env=_clean_env()
        )
        r = subprocess.run(
            ["systemctl", "enable", "--now", _SERVICE_NAME],
            capture_output=True, text=True, timeout=30, env=_clean_env()
        )
        if r.returncode == 0:
            steps.append("Enabled and started oxpec-load service")
            _log_info("oxpec service enabled and started")
        else:
            _log_error(f"systemctl enable --now failed: {r.stderr.strip()}")
            # Try loading manually as fallback
            load_result = {"success": False}
            if modprobe_works:
                load_result = _try_modprobe()
            if not load_result["success"]:
                insmod_path = ko_for_service or _INSTALL_KO
                if os.path.exists(insmod_path):
                    load_result = _try_insmod(insmod_path)
            if load_result["success"]:
                steps.append("Loaded module manually (service failed)")
                _log_warning("Service failed but manual load succeeded")
            else:
                return {"success": False, "error": f"Failed to load module: {r.stderr.strip()}", "steps": steps}
    except Exception as e:
        return {"success": False, "error": f"systemctl failed: {e}", "steps": steps}

    # Verify
    if _is_module_loaded():
        steps.append("Module loaded successfully")
        _log_info("oxpec loaded")
        sysfs_nodes = _wait_for_sysfs_nodes()
        _log_sysfs_nodes(sysfs_nodes)
        hwmon = _find_hwmon()
        if hwmon:
            steps.append(f"hwmon device at {hwmon}")
        if sysfs_nodes.get("turbo_toggle_nodes"):
            steps.append(f"tt_toggle at {sysfs_nodes['turbo_toggle_nodes'][0]}")
        if sysfs_nodes.get("fan_control_nodes"):
            steps.append(f"fan node at {sysfs_nodes['fan_control_nodes'][0]}")
        _log_info("oxpec applied successfully")
        return {"success": True, "message": "oxpec driver loaded", "steps": steps}
    else:
        return {"success": False, "error": "Module did not load after install", "steps": steps}


def revert():
    """Unload oxpec and remove service."""
    steps = []
    _log_info("=== oxpec Revert Start ===")

    # Disable and stop service
    if os.path.exists(_SERVICE_PATH):
        try:
            subprocess.run(
                ["systemctl", "disable", "--now", _SERVICE_NAME],
                capture_output=True, text=True, timeout=30, env=_clean_env()
            )
            steps.append("Disabled oxpec-load service")
        except Exception as e:
            _log_warning(f"Failed to disable service: {e}")

    # Unload module
    if _is_module_loaded():
        try:
            r = subprocess.run(
                ["rmmod", "oxpec"],
                capture_output=True, text=True, timeout=10, env=_clean_env()
            )
            if r.returncode == 0:
                steps.append("Unloaded oxpec module")
                _log_info("oxpec module unloaded")
            else:
                _log_warning(f"rmmod failed: {r.stderr.strip()}")
                steps.append(f"rmmod failed: {r.stderr.strip()}")
        except Exception as e:
            _log_warning(f"rmmod exception: {e}")

    # Remove service file
    if os.path.exists(_SERVICE_PATH):
        try:
            os.remove(_SERVICE_PATH)
            steps.append("Removed service file")
        except Exception as e:
            _log_warning(f"Failed to remove service file: {e}")

    # Remove installed .ko
    if os.path.isdir(_INSTALL_DIR):
        try:
            import shutil
            shutil.rmtree(_INSTALL_DIR)
            steps.append("Removed /var/lib/oxpec/")
        except Exception as e:
            _log_warning(f"Failed to remove install dir: {e}")

    # Reload systemd
    try:
        subprocess.run(
            ["systemctl", "daemon-reload"],
            capture_output=True, text=True, timeout=30, env=_clean_env()
        )
    except Exception:
        pass

    _log_info("oxpec reverted")
    return {"success": True, "message": "oxpec driver unloaded and service removed", "steps": steps}
