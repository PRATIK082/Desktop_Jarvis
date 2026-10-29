// Layout preferences persisted to localStorage so the adaptive UI
// (resizable panels, transparency, compact mode) survives reloads.
import { useCallback, useState } from "react";

export interface LayoutPrefs {
  panelOpacity: number; // 0.4 .. 1.0
  compact: boolean;
  navCollapsed: boolean;
  rightPanelWidth: number; // px
}

const STORAGE_KEY = "jarvis.layoutPrefs.v1";

const DEFAULTS: LayoutPrefs = {
  panelOpacity: 1,
  compact: false,
  navCollapsed: false,
  rightPanelWidth: 320,
};

function readPrefs(): LayoutPrefs {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULTS };
    const parsed = JSON.parse(raw) as Partial<LayoutPrefs>;
    return {
      panelOpacity: clamp(
        typeof parsed.panelOpacity === "number"
          ? parsed.panelOpacity
          : DEFAULTS.panelOpacity,
        0.4,
        1,
      ),
      compact: Boolean(parsed.compact),
      navCollapsed: Boolean(parsed.navCollapsed),
      rightPanelWidth: clamp(
        typeof parsed.rightPanelWidth === "number"
          ? parsed.rightPanelWidth
          : DEFAULTS.rightPanelWidth,
        240,
        520,
      ),
    };
  } catch {
    return { ...DEFAULTS };
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function useLayoutPrefs() {
  const [prefs, setPrefs] = useState<LayoutPrefs>(() => readPrefs());

  const update = useCallback((patch: Partial<LayoutPrefs>) => {
    setPrefs((prev) => {
      const next: LayoutPrefs = { ...prev, ...patch };
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // storage unavailable; keep in-memory only
      }
      return next;
    });
  }, []);

  return { prefs, update };
}
