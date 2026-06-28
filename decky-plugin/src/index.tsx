import { useState, useEffect, useCallback, FC } from "react";
import { PanelSection, PanelSectionRow, staticClasses } from "@decky/ui";
import { definePlugin } from "@decky/api";
import { BUILD_ID } from "./build_info";
import type { OxpecStatus, LoadingState, ResultMessage, TurboOverlayStatus } from "./types";
import { getStatus } from "./rpc";
import { FixesSection } from "./FixesSection";
import { LogsSection } from "./LogsSection";

const Content: FC = () => {
  const [oxpec, setOxpec] = useState<OxpecStatus>({ applied: false });
  const [turboOverlay, setTurboOverlay] = useState<TurboOverlayStatus>({
    enabled: true,
    running: false,
    tt_toggle_startup_enabled: true,
    tt_toggle_paths: [],
    is_superx: false,
  });
  const [statusLoaded, setStatusLoaded] = useState(false);
  const [loading, setLoading] = useState<LoadingState>({ active: null, message: "" });
  const [result, setResult] = useState<ResultMessage | null>(null);

  const showResult = useCallback((key: string, text: string, type: "success" | "error") => {
    setResult({ key, text, type });
    setTimeout(() => setResult((prev) => (prev?.key === key ? null : prev)), 4000);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const status = await getStatus();
      setOxpec(status.oxpec);
      setTurboOverlay(status.turbo_overlay);
    } catch (e) {
      console.error("Failed to get status:", e);
    } finally {
      setStatusLoaded(true);
    }
  }, []);

  // Initial load
  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <>
      {/* Warning Banner */}
      <PanelSection>
        <PanelSectionRow>
          <div
            style={{
              backgroundColor: "#4a3000",
              border: "1px solid #7a5000",
              borderRadius: "4px",
              padding: "8px 12px",
              fontSize: "12px",
              lineHeight: "1.4",
              color: "#ffcc00",
            }}
          >
            <strong>Use at your own risk.</strong> This plugin modifies system files and hardware
            settings. This v0.1 build is limited to oxpec EC support for ONEXPLAYER SUPER X.
          </div>
        </PanelSectionRow>
      </PanelSection>

      <FixesSection
        oxpec={oxpec}
        setOxpec={setOxpec}
        turboOverlay={turboOverlay}
        setTurboOverlay={setTurboOverlay}
        loading={loading}
        setLoading={setLoading}
        showResult={showResult}
        result={result}
        statusLoaded={statusLoaded}
        refresh={refresh}
      />

      <LogsSection
        loading={loading}
        setLoading={setLoading}
        showResult={showResult}
        result={result}
      />

      {/* Build info */}
      <div style={{ textAlign: "center", fontSize: "10px", opacity: 0.3, padding: "4px 0" }}>
        {BUILD_ID}
      </div>
    </>
  );
};

export default definePlugin(() => ({
  name: "ONEXPLAYER SUPER X Tools",
  titleView: <div className={staticClasses.Title}>OXP Super X Tools</div>,
  content: <Content />,
  icon: (
    <svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20">
      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z" />
    </svg>
  ),
}));
