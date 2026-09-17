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
import { LAYOUT, type Density } from "./tokens";

interface AppearanceContextValue {
  appearance: Appearance;
  /** What `system` currently resolves to. */
  mode: "light" | "dark";
  density: Density;
  setAppearance: (next: Appearance) => void;
  setDensity: (next: Density) => void;
  chartTheme: ReturnType<typeof buildChartTheme>;
}

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

/** Below this the app is being held, not pointed at (§56). */
const HANDHELD = `(max-width: ${LAYOUT.breakpoints.mobile - 1}px)`;

function isHandheld(): boolean {
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
  if (!window.matchMedia) return false;
  return window.matchMedia(HANDHELD).matches;
}

export function AppearanceProvider({ children }: { children: ReactNode }) {
  const [appearance, setAppearanceState] = useState<Appearance>(() =>
    read(STORAGE_KEYS.appearance, "system", ["light", "dark", "system"] as const),
  );
  const [density, setDensityState] = useState<Density>(() =>
    read(STORAGE_KEYS.density, "middle", ["compact", "middle", "comfortable"] as const),
  );
  const [systemMode, setSystemMode] = useState<"light" | "dark">(() =>
    resolveAppearance("system"),
  );
  const [handheld, setHandheld] = useState<boolean>(() => isHandheld());

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

  // And follow the *width*, for the same reason: a control sized for a mouse
  // is not a control a thumb can hit.
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
    if (!window.matchMedia) return;
    const query = window.matchMedia(HANDHELD);
    const listener = (event: MediaQueryListEvent) => setHandheld(event.matches);
    query.addEventListener("change", listener);
    return () => query.removeEventListener("change", listener);
  }, []);

  const mode = appearance === "system" ? systemMode : appearance;

  /**
   * The density actually rendered, which on a phone is not always the one the
   * reader chose (§56).
   *
   * `compact` is a *mouse* setting: 28px controls and 21px small buttons, which
   * is right for somebody comparing forty rows with a pointer and unusable
   * with a thumb — WCAG 2.2 asks for 24×24 as a minimum and a compact phone
   * misses it. So a handheld width floors the density at `middle` while
   * leaving the stored preference alone: the reader's choice still applies on
   * the machine they made it on, and the preferences page still shows it.
   */
  const rendered: Density = handheld && density === "compact" ? "middle" : density;

  const setAppearance = useCallback((next: Appearance) => {
    setAppearanceState(next);
    write(STORAGE_KEYS.appearance, next);
  }, []);

  const setDensity = useCallback((next: Density) => {
    setDensityState(next);
    write(STORAGE_KEYS.density, next);
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
    () => ({ appearance, mode, density, setAppearance, setDensity, chartTheme }),
    [appearance, mode, density, setAppearance, setDensity, chartTheme],
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
