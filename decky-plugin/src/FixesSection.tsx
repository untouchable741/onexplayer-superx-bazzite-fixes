import { FC } from "react";
import {
  ButtonItem,
  PanelSection,
  PanelSectionRow,
  ToggleField,
} from "@decky/ui";
import type { LoadingState, ResultMessage, OxpecStatus, TurboOverlayStatus } from "./types";
import { applyOxpec, rebuildOxpec, revertOxpec, setDebugLoggingEnabled, setTtToggleStartupEnabled, setTurboOverlayEnabled } from "./rpc";
import { InlineStatus } from "./InlineStatus";

const NodeList: FC<{ title: string; nodes?: string[] }> = ({ title, nodes }) => (
  <div style={{ marginTop: "6px" }}>
    <strong>{title}:</strong>{" "}
    {nodes && nodes.length > 0 ? nodes.join(", ") : "not detected yet"}
  </div>
);

export const FixesSection: FC<{
  oxpec: OxpecStatus;
  setOxpec: React.Dispatch<React.SetStateAction<OxpecStatus>>;
  turboOverlay: TurboOverlayStatus;
  setTurboOverlay: React.Dispatch<React.SetStateAction<TurboOverlayStatus>>;
  loading: LoadingState;
  setLoading: (l: LoadingState) => void;
  showResult: (key: string, text: string, type: "success" | "error") => void;
  result: ResultMessage | null;
  statusLoaded: boolean;
  refresh: () => Promise<void>;
}> = ({ oxpec, setOxpec, turboOverlay, setTurboOverlay, loading, setLoading, showResult, result, statusLoaded, refresh }) => {
  const handleOxpec = async (enabled: boolean) => {
    setLoading({
      active: "oxpec",
      message: enabled ? "Installing oxpec driver..." : "Removing oxpec driver...",
    });
    try {
      const res = enabled ? await applyOxpec() : await revertOxpec();
      if (res.success) {
        setOxpec((prev) => ({ ...prev, applied: enabled }));
        showResult("oxpec", res.message || (enabled ? "Installed" : "Removed"), "success");
      } else {
        showResult("oxpec", res.error || "Failed", "error");
      }
    } catch (e) {
      showResult("oxpec", `Error: ${e}`, "error");
    } finally {
      setLoading({ active: null, message: "" });
      refresh();
    }
  };

  const handleTurboOverlay = async (enabled: boolean) => {
    setLoading({
      active: "turboOverlay",
      message: enabled ? "Starting Turbo watcher..." : "Stopping Turbo watcher...",
    });
    try {
      const res = await setTurboOverlayEnabled(enabled);
      if (res.success) {
        setTurboOverlay((prev) => ({ ...prev, enabled }));
        showResult("turboOverlay", res.message || "Updated", "success");
      } else {
        showResult("turboOverlay", res.error || "Failed", "error");
      }
    } catch (e) {
      showResult("turboOverlay", `Error: ${e}`, "error");
    } finally {
      setLoading({ active: null, message: "" });
      refresh();
    }
  };

  const handleTtToggleStartup = async (enabled: boolean) => {
    setLoading({
      active: "ttToggle",
      message: enabled ? "Enabling tt_toggle..." : "Disabling startup tt_toggle...",
    });
    try {
      const res = await setTtToggleStartupEnabled(enabled);
      if (res.success) {
        setTurboOverlay((prev) => ({ ...prev, tt_toggle_startup_enabled: enabled }));
        showResult("ttToggle", res.message || "Updated", "success");
      } else {
        showResult("ttToggle", res.error || "Failed", "error");
      }
    } catch (e) {
      showResult("ttToggle", `Error: ${e}`, "error");
    } finally {
      setLoading({ active: null, message: "" });
      refresh();
    }
  };

  const handleDebugLogging = async (enabled: boolean) => {
    setLoading({
      active: "debugLogging",
      message: enabled ? "Enabling debug logging..." : "Disabling debug logging...",
    });
    try {
      const res = await setDebugLoggingEnabled(enabled);
      if (res.success) {
        setTurboOverlay((prev) => ({ ...prev, debug_logging_enabled: enabled }));
        showResult("debugLogging", res.message || "Updated", "success");
      } else {
        showResult("debugLogging", res.error || "Failed", "error");
      }
    } catch (e) {
      showResult("debugLogging", `Error: ${e}`, "error");
    } finally {
      setLoading({ active: null, message: "" });
      refresh();
    }
  };

  const handleRebuildOxpec = async () => {
    setLoading({
      active: "rebuildOxpec",
      message: "Rebuilding oxpec.ko...",
    });
    try {
      const res = await rebuildOxpec();
      if (res.success) {
        showResult("rebuildOxpec", res.message || "Rebuilt oxpec.ko", "success");
      } else {
        showResult("rebuildOxpec", res.error || "Rebuild failed", "error");
      }
    } catch (e) {
      showResult("rebuildOxpec", `Error: ${e}`, "error");
    } finally {
      setLoading({ active: null, message: "" });
      refresh();
    }
  };

  return (
    <PanelSection title="EC Driver">
      {!statusLoaded ? (
        <PanelSectionRow>
          <div style={{ fontSize: "12px", color: "#aaa", padding: "8px 0" }}>
            Loading status...
          </div>
        </PanelSectionRow>
      ) : (
        <>
          <PanelSectionRow>
            <ToggleField
              label="EC Sensor Driver (oxpec)"
              description={
                oxpec.applied
                  ? `Loaded (${oxpec.load_method === "modprobe" ? "kernel" : "bundled"})${oxpec.hwmon_path ? " - hwmon active" : ""}`
                  : oxpec.error && oxpec.error !== "module not loaded"
                    ? `Error: ${oxpec.error}`
                    : "Enables fan hwmon nodes and charge controls"
              }
              checked={oxpec.applied}
              disabled={loading.active === "oxpec"}
              onChange={handleOxpec}
            />
          </PanelSectionRow>
          <InlineStatus loading={loading} result={result} section="oxpec" />
          {oxpec.kernel_mismatch && (
            <PanelSectionRow>
              <div
                style={{
                  backgroundColor: "#4a3000",
                  border: "1px solid #7a5000",
                  borderRadius: "4px",
                  padding: "8px 12px",
                  fontSize: "11px",
                  lineHeight: "1.4",
                  color: "#ffcc00",
                }}
              >
                {oxpec.kernel_mismatch_message || "Kernel mismatch. Rebuild oxpec.ko for current kernel."}{" "}
                Current kernel: <strong>{oxpec.running_kernel || "unknown"}</strong>.
                {oxpec.bundled_kernels && oxpec.bundled_kernels.length > 0
                  ? <> Available: {oxpec.bundled_kernels.join(", ")}.</>
                  : <> No bundled modules available.</>
                } {oxpec.mismatch_vermagic ? <>Bundled vermagic: {oxpec.mismatch_vermagic}.</> : null}
              </div>
            </PanelSectionRow>
          )}
          {oxpec.kernel_mismatch && (
            <PanelSectionRow>
              <ButtonItem
                layout="below"
                onClick={handleRebuildOxpec}
                disabled={loading.active === "rebuildOxpec" || loading.active === "oxpec"}
              >
                Rebuild oxpec
              </ButtonItem>
            </PanelSectionRow>
          )}
          <InlineStatus loading={loading} result={result} section="rebuildOxpec" />
          <PanelSectionRow>
            <div
              style={{
                backgroundColor: "#1a2a3a",
                border: "1px solid #2a4a6a",
                borderRadius: "4px",
                padding: "8px 12px",
                fontSize: "11px",
                lineHeight: "1.4",
                color: "#88bbdd",
              }}
            >
              <div><strong>Kernel:</strong> {oxpec.running_kernel || "unknown"}</div>
              <div><strong>Bundled vermagic:</strong> {oxpec.bundled_vermagic || oxpec.mismatch_vermagic || "not detected"}</div>
              <div><strong>hwmon:</strong> {oxpec.hwmon_path || "not detected yet"}</div>
              <NodeList title="Fan nodes" nodes={oxpec.fan_control_nodes} />
              <NodeList title="Charge nodes" nodes={oxpec.charge_control_nodes} />
              <NodeList title="Turbo takeover nodes" nodes={oxpec.turbo_toggle_nodes} />
              <div><strong>Turbo watcher:</strong> {turboOverlay.running ? "running" : "stopped"}</div>
              <div><strong>Watched devices:</strong> {turboOverlay.watched_device_count ?? 0}</div>
              <div><strong>Debug logging:</strong> {turboOverlay.debug_logging_enabled ? "enabled" : "disabled"}</div>
              {turboOverlay.task_id ? <div><strong>Task:</strong> {turboOverlay.task_id}</div> : null}
            </div>
          </PanelSectionRow>
          <PanelSectionRow>
            <ToggleField
              label="Turbo -> HHD Overlay"
              description={
                turboOverlay.is_superx
                  ? turboOverlay.running
                    ? "Watching evdev for Ctrl+Meta+Alt"
                    : "Detect Ctrl+Meta+Alt and toggle HHD overlay"
                  : `DMI mismatch: ${turboOverlay.board_vendor || "unknown"} / ${turboOverlay.board_name || "unknown"}`
              }
              checked={turboOverlay.enabled}
              disabled={loading.active === "turboOverlay" || !turboOverlay.is_superx}
              onChange={handleTurboOverlay}
            />
          </PanelSectionRow>
          <InlineStatus loading={loading} result={result} section="turboOverlay" />
          <PanelSectionRow>
            <ToggleField
              label="Debug logging"
              description={
                turboOverlay.debug_logging_enabled
                  ? "Verbose device/key/API logs enabled"
                  : "Off by default; enable only for troubleshooting"
              }
              checked={turboOverlay.debug_logging_enabled}
              disabled={loading.active === "debugLogging"}
              onChange={handleDebugLogging}
            />
          </PanelSectionRow>
          <InlineStatus loading={loading} result={result} section="debugLogging" />
          <PanelSectionRow>
            <ToggleField
              label="Enable tt_toggle on Startup"
              description={
                turboOverlay.tt_toggle_paths.length > 0
                  ? `Found: ${turboOverlay.tt_toggle_paths.join(", ")}`
                  : "tt_toggle not detected"
              }
              checked={turboOverlay.tt_toggle_startup_enabled}
              disabled={loading.active === "ttToggle" || !turboOverlay.is_superx}
              onChange={handleTtToggleStartup}
            />
          </PanelSectionRow>
          <InlineStatus loading={loading} result={result} section="ttToggle" />
          <PanelSectionRow>
            <div
              style={{
                backgroundColor: "#2f2f2f",
                border: "1px solid #555",
                borderRadius: "4px",
                padding: "8px 12px",
                fontSize: "11px",
                lineHeight: "1.4",
                color: "#ddd",
              }}
            >
              Super X v0.9-beta keeps stock HHD and does not apply Apex
              controller patches. Official Windows TDP limits are 75W on AC
              power and 55W on battery; do not use 120W even if HHD exposes it.
              Ctrl+Meta+Alt from an external keyboard also opens the overlay in
              this preview.
            </div>
          </PanelSectionRow>
        </>
      )}
    </PanelSection>
  );
};
