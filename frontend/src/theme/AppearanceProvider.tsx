/**
 * Appearance and density, applied to AntD and to the stylesheet at once.
 *
 * Both settings live here rather than in each screen because both change the
 * *shape* of every screen: a density switch that only reached the table would
 * leave the toolbar above it at a different height, which is worse than not
 * offering the switch at all.
 *
 * The choice is written to localStorage immediately so a reload does not flash
 * the wrong theme, and synced to the user's profile (§40) once auth exists —
 * localStorage is the fast path, the server is the durable one.
 */

import { ConfigProvider } from "antd";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { STORAGE_KEYS } from "@/config";

import { buildTheme, cssVariables, resolveAppearance, type Appearance } from "./antd";
import { buildChartTheme } from "./echarts";
import { type Density } from "./tokens";

interface AppearanceContextValue {
  appearance: Appearance;
  /** What `system` currently resolves to. */
  mode: "light" | "dark";
  density: Density;
  setAppearance: (next: Appearance) => void;
  chartTheme: ReturnType<typeof buildChartTheme>;
}

/**
 * The one spacing this application has.
 *
 * Density used to be a setting. It is not one here: a control that every
 * reader leaves alone is a control that costs a place in the header and a
 * decision on first use, and the roomy scale is the one this app is designed
 * at — record prose, chart cards and a table of long video names all want the
 * air. The token scale itself still supports the other two (`DENSITY` in
 * tokens.ts); nothing in the UI selects them.
 */
const DENSITY_CHOICE: Density = "comfortable";

const AppearanceContext = createContext<AppearanceContextValue | null>(null);

function read<T extends string>(key: string, fallback: T, allowed: readonly T[]): T {
  try {
    const stored = window.localStorage.getItem(key);
    return stored && (allowed as readonly string[]).includes(stored) ? (stored as T) : fallback;
  } catch {
    // Private browsing, or storage disabled. The default is a working app.
    return fallback;
  }
}

function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* not worth failing a render over */
  }
}

export function AppearanceProvider({ children }: { children: ReactNode }) {
  const [appearance, setAppearanceState] = useState<Appearance>(() =>
    read(STORAGE_KEYS.appearance, "system", ["light", "dark", "system"] as const),
  );
  // Fixed, and deliberately not read back from localStorage: a reader who
  // chose `compact` before the switch was removed would otherwise be stuck
  // with it and have no way to leave.
  const density: Density = DENSITY_CHOICE;
  const [systemMode, setSystemMode] = useState<"light" | "dark">(() =>
    resolveAppearance("system"),
  );

  // Follow the OS while the setting is `system`, and keep following it — a
  // laptop that switches to dark at sunset should take the app with it.
  useEffect(() => {
    // The DOM types say `matchMedia` is always there; jsdom says otherwise,
    // which is why `test/setup.ts` polyfills it. The guard is not dead code.
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
    if (!window.matchMedia) return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const listener = (event: MediaQueryListEvent) => setSystemMode(event.matches ? "dark" : "light");
    query.addEventListener("change", listener);
    return () => query.removeEventListener("change", listener);
  }, []);

  const mode = appearance === "system" ? systemMode : appearance;

  const rendered: Density = density;

  const setAppearance = useCallback((next: Appearance) => {
    setAppearanceState(next);
    write(STORAGE_KEYS.appearance, next);
  }, []);

  // The stylesheet reads these; AntD components read the theme below. Both are
  // derived from the same tokens, so they cannot disagree.
  useEffect(() => {
    const root = document.documentElement;
    for (const [name, value] of Object.entries(cssVariables(appearance, rendered))) {
      root.style.setProperty(name, value);
    }
    root.dataset["theme"] = mode;
    // The *rendered* density, because the stylesheet's rows and controls are
    // sized from it — and a test or a screenshot asking "what is on screen"
    // should read what is on screen.
    root.dataset["density"] = rendered;
    // Tells the browser to paint form controls and scrollbars to match.
    root.style.colorScheme = mode;
  }, [appearance, rendered, mode]);

  const theme = useMemo(() => buildTheme(appearance, rendered), [appearance, rendered]);
  const chartTheme = useMemo(() => buildChartTheme(mode, rendered), [mode, rendered]);

  const value = useMemo(
    () => ({ appearance, mode, density, setAppearance, chartTheme }),
    [appearance, mode, density, setAppearance, chartTheme],
  );

  return (
    <AppearanceContext.Provider value={value}>
      <ConfigProvider theme={theme} componentSize={rendered === "compact" ? "small" : "middle"}>
        {children}
      </ConfigProvider>
    </AppearanceContext.Provider>
  );
}

export function useAppearance(): AppearanceContextValue {
  const value = useContext(AppearanceContext);
  if (!value) throw new Error("useAppearance must be used inside <AppearanceProvider>");
  return value;
}
