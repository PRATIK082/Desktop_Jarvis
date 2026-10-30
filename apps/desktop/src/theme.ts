// HUD accent theming (E3c).
//
// Accent colors are CSS variables (--accent, --accent-2) so presets apply
// at runtime without rebuilding Tailwind classes. tailwind.config.js maps
// accent-cyan/accent-blue onto these variables; this module owns the
// preset definitions, custom-hue math, localStorage persistence, and
// application to document.documentElement.

export interface AccentPreset {
  id: string;
  label: string;
  accent: [number, number, number];
  accent2: [number, number, number];
}

export const ACCENT_PRESETS: AccentPreset[] = [
  {
    id: "cyan",
    label: "Cyan",
    accent: [34, 211, 238],
    accent2: [59, 130, 246],
  },
  {
    id: "blue",
    label: "Blue",
    accent: [96, 165, 250],
    accent2: [34, 211, 238],
  },
  {
    id: "violet",
    label: "Violet",
    accent: [167, 139, 250],
    accent2: [236, 72, 153],
  },
  {
    id: "amber",
    label: "Amber",
    accent: [251, 191, 36],
    accent2: [249, 115, 22],
  },
  {
    id: "green",
    label: "Green",
    accent: [74, 222, 128],
    accent2: [45, 212, 191],
  },
];

export interface AccentSelection {
  /** Preset id, or "custom" for the hue-slider color. */
  preset: string;
  /** Hue in degrees (0-359); used when preset === "custom". */
  hue: number;
}

const STORAGE_KEY = "jarvis-accent";

export const DEFAULT_ACCENT: AccentSelection = { preset: "cyan", hue: 187 };

function hslToRgb(h: number, s: number, l: number): [number, number, number] {
  const c = ((1 - Math.abs(2 * l - 1)) * s) / 100;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  let r = 0;
  let g = 0;
  let b = 0;
  if (h < 60) {
    r = c;
    g = x;
  } else if (h < 120) {
    r = x;
    g = c;
  } else if (h < 180) {
    g = c;
    b = x;
  } else if (h < 240) {
    g = x;
    b = c;
  } else if (h < 300) {
    r = x;
    b = c;
  } else {
    r = c;
    b = x;
  }
  return [
    Math.round((r + m) * 255),
    Math.round((g + m) * 255),
    Math.round((b + m) * 255),
  ];
}

function normalizeHue(hue: number): number {
  return ((Math.round(hue) % 360) + 360) % 360;
}

export function resolveAccent(sel: AccentSelection): {
  accent: [number, number, number];
  accent2: [number, number, number];
} {
  if (sel.preset !== "custom") {
    const found = ACCENT_PRESETS.find((p) => p.id === sel.preset);
    const preset = found ?? ACCENT_PRESETS[0];
    return { accent: preset.accent, accent2: preset.accent2 };
  }
  const hue = normalizeHue(sel.hue);
  return {
    accent: hslToRgb(hue, 90, 65),
    accent2: hslToRgb((hue + 40) % 360, 85, 60),
  };
}

export function applyAccent(sel: AccentSelection): void {
  if (typeof document === "undefined") return;
  const { accent, accent2 } = resolveAccent(sel);
  const root = document.documentElement;
  root.style.setProperty("--accent", `${accent[0]} ${accent[1]} ${accent[2]}`);
  root.style.setProperty(
    "--accent-2",
    `${accent2[0]} ${accent2[1]} ${accent2[2]}`,
  );
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sel));
  } catch {
    // Storage unavailable (private mode): theme still applies for session.
  }
}

export function loadAccent(): AccentSelection {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_ACCENT;
    const parsed = JSON.parse(raw) as Partial<AccentSelection>;
    const hue =
      typeof parsed.hue === "number" && Number.isFinite(parsed.hue)
        ? normalizeHue(parsed.hue)
        : DEFAULT_ACCENT.hue;
    const preset =
      typeof parsed.preset === "string" ? parsed.preset : DEFAULT_ACCENT.preset;
    if (preset !== "custom" && !ACCENT_PRESETS.some((p) => p.id === preset)) {
      return DEFAULT_ACCENT;
    }
    return { preset, hue };
  } catch {
    return DEFAULT_ACCENT;
  }
}

/** Load the persisted accent (or default) and apply it. Call once on mount. */
export function applyStoredAccent(): void {
  applyAccent(loadAccent());
}
