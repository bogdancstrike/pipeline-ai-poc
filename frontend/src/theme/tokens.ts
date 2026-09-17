/**
 * The design tokens. One source, three consumers.
 *
 * The AntD theme, the CSS custom properties and the ECharts theme are all
 * derived from this file. That is the whole point: a platform where the table
 * is themed by one system and the chart beside it by another is a platform
 * where the two drift, and the drift is always visible precisely where a
 * reader is comparing them.
 *
 * Rules this encodes:
 *
 * - **Colour means something.** Status, severity and health get colour;
 *   nothing else does. There is one accent, and it is the logo's core.
 * - **Density is a first-class axis.** Enterprise users compare rows. The
 *   compact scale is not an afterthought bolted on for mobile.
 * - **Status colours are fixed per vocabulary**, so one status is one colour on
 *   the board, in the table and in the chart.
 */

export const NEUTRAL = {
  50: "#f8fafc",
  100: "#f1f5f9",
  200: "#e2e8f0",
  300: "#cbd5e1",
  400: "#94a3b8",
  // Darkened from #64748b, which cleared 4.5:1 on a card (4.76) and missed it
  // on the *page* ground (4.34) — and tertiary text lands on both. See
  // `theme/contrast.test.ts`, which is what caught it.
  500: "#5f6e85",
  600: "#475569",
  700: "#334155",
  800: "#1e293b",
  900: "#0f172a",
  950: "#020617",
} as const;

/**
 * The dark ramp — near-neutral charcoal, deliberately not slate inverted.
 *
 * Slate carries a blue cast that is invisible at 95% lightness and unmissable
 * at 8%: a "dark" surface built from `NEUTRAL[900]` reads as navy, and the
 * whole product looks like it has a blue theme nobody asked for. These greys
 * are almost achromatic, so what the eye notices in dark mode is the accent
 * and the status colours — which is the only thing that should carry hue.
 *
 * Numbered by darkness like the light ramp, so `INK[800]` and `NEUTRAL[100]`
 * play the same structural role in their respective modes.
 */
export const INK = {
  950: "#08090c",
  900: "#0b0c10",
  850: "#0e0f14",
  800: "#15171c",
  750: "#1b1e24",
  700: "#232730",
  650: "#262a33",
  600: "#343a45",
  500: "#4a515e",
  // Raised from #6b7383, which axe caught on a `Descriptions` label: 3.76:1
  // against the dark panel, under the 4.5:1 text threshold (§55, §64). AntD
  // uses `colorTextTertiary` for label text, not only for hints, so the ramp
  // has to hold at 4.5 all the way down. #7d8595 is 4.83:1 and still a step
  // quieter than INK[300].
  400: "#7d8595",
  300: "#9aa2b1",
  200: "#c3c8d2",
  100: "#e8eaf0",
} as const;

/**
 * The light surface. The one ground that is not a step of a ramp.
 *
 * Named so that "white" is a token like everything else: a `#ffffff` typed
 * into a component is indistinguishable from a `#ffffff` that means "the card
 * behind this", and only one of them should survive a change of theme.
 */
export const PAPER = "#ffffff";

/**
 * The logo's own three colours, and the one thing in the product that does
 * *not* follow the palette.
 *
 * A brand mark that changes hue with the theme is not a brand mark. The middle
 * value is the accent because the accent was taken *from* the logo — that is
 * the direction of the dependency, and writing it here keeps somebody from
 * "fixing" the mark when they retune the accent.
 */
export const LOGO = {
  ring: "#8b8bf0",
  core: "#5b5bd6",
  spark: "#22d3ee",
} as const;

export const ACCENT = {
  50: "#eeeefc",
  100: "#dcdcf9",
  200: "#bcbcf3",
  300: "#9a9aec",
  400: "#7c7cf5",
  500: "#5b5bd6",
  600: "#4a4ac0",
  700: "#4338ca",
  800: "#332f96",
  900: "#272470",
} as const;

export const SEMANTIC = {
  success: "#16a34a",
  warning: "#ca8a04",
  danger: "#dc2626",
  info: "#0891b2",
  neutral: NEUTRAL[500],
} as const;

/**
 * The same four meanings, at a lightness that can be *read*.
 *
 * `SEMANTIC` is tuned for fills — a bar, a dot, a lane rule — where the bar to
 * clear is 3:1 against the surface. Small text has to clear 4.5:1, and the
 * fills do not: amber `#ca8a04` on white is 2.9:1, and green `#16a34a` is
 * 3.3:1. A page that colours a sentence with them has written a sentence a
 * third of its readers cannot read.
 *
 * So the two are separated rather than compromised. Nothing gets a worse fill
 * to make a caption legible, and nothing gets an illegible caption to match a
 * bar. Both carry the same *meaning*, which is what has to agree.
 */
/**
 * The ground an initials avatar is drawn on, in both appearances.
 *
 * AntD's default is `#bfbfbf`, which carries white text at 1.84:1 — so every
 * avatar in the product without a photograph was illegible, and axe found it
 * only on the first page that draws a column of them. One value for both
 * appearances on purpose: an avatar is an identity marker and should not
 * change colour when somebody switches theme.
 */
export const AVATAR_GROUND = "#475569";

export const SEMANTIC_INK = {
  light: {
    // A step darker than the ink used on white, because these also land on
    // AntD's *tinted* backgrounds — a warning tag is amber on `#fffbe6`, and
    // `#a16207` there is 4.73:1 while the amber it derives is 2.82:1. One
    // value that clears the bar on both grounds beats two that each clear one.
    //
    // How dark a step depends on the tint, and the tints are *derived from
    // `SEMANTIC`* rather than AntD's stock seeds: our success and info greens
    // are saturated enough that the ramp desaturates their tints to `#d3e3d6`
    // and `#daf1f2` instead of the near-white `#f6ffed` and `#e6f4ff`. So
    // these two carry a further step. The worst ground each value has to
    // survive, and what it scores there:
    //
    //   success  #166534 on #d3e3d6  5.34:1   (#15803d was 3.76:1 — failed)
    //   warning  #854d0e on #fffbe6  6.59:1
    //   danger   #b91c1c on #fff2f0  5.92:1
    //   info     #155e75 on #daf1f2  6.18:1   (#0e7490 was 4.55:1 — passed
    //                                          by 0.05, which a hover ground
    //                                          or a nested tint undoes)
    //
    // Small text at 10px — a tag under compact density — is held to 4.5:1,
    // and none of these is ever the *only* carrier of its meaning (§64).
    success: "#166534",
    warning: "#854d0e",
    danger: "#b91c1c",
    info: "#155e75",
  },
  dark: {
    success: "#4ade80",
    warning: "#fbbf24",
    danger: "#f87171",
    info: "#22d3ee",
  },
} as const;

/**
 * The categorical series palette for charts.
 *
 * Ordered so that adjacent series are distinguishable by hue *and* by
 * lightness — a chart read in greyscale, or by a reader with deuteranopia,
 * still separates the first four series, which is as many as most charts have.
 */
export const SERIES = [
  "#5b5bd6",
  "#0891b2",
  "#16a34a",
  "#ca8a04",
  "#db2777",
  "#7c3aed",
  "#0d9488",
  "#ea580c",
  "#64748b",
  "#4338ca",
] as const;

/**
 * Status → colour, per domain vocabulary.
 *
 * Keyed by the exact strings the API returns, so a component never has to map
 * a status to a colour itself and two components can never disagree.
 */
export const STATUS_COLORS: Record<string, string> = {
  // lifecycle
  ACTIVE: SEMANTIC.success,
  INACTIVE: NEUTRAL[400],
  SUSPENDED: SEMANTIC.warning,
  LOCKED: SEMANTIC.danger,
  INVITED: SEMANTIC.info,
  ARCHIVED: NEUTRAL[400],
  BLOCKED: SEMANTIC.danger,

  // work
  NEW: SEMANTIC.info,
  ASSIGNED: "#7c3aed",
  IN_PROGRESS: ACCENT[500],
  IN_REVIEW: "#0d9488",
  DONE: SEMANTIC.success,
  COMPLETED: SEMANTIC.success,
  CANCELLED: NEUTRAL[400],
  ON_HOLD: SEMANTIC.warning,
  PLANNING: NEUTRAL[500],

  // support
  OPEN: SEMANTIC.info,
  WAITING_CUSTOMER: SEMANTIC.warning,
  ESCALATED: SEMANTIC.danger,
  RESOLVED: SEMANTIC.success,
  CLOSED: NEUTRAL[400],

  // commerce
  PENDING: SEMANTIC.warning,
  CONFIRMED: SEMANTIC.info,
  PROCESSING: ACCENT[500],
  SHIPPED: "#0d9488",
  DELIVERED: SEMANTIC.success,
  REFUNDED: NEUTRAL[500],
  PAID: SEMANTIC.success,
  UNPAID: SEMANTIC.warning,
  PARTIAL: SEMANTIC.warning,
  OVERDUE: SEMANTIC.danger,

  // operations
  QUEUED: NEUTRAL[500],
  RUNNING: ACCENT[500],
  SUCCEEDED: SEMANTIC.success,
  FAILED: SEMANTIC.danger,
  RETRYING: SEMANTIC.warning,
  HEALTHY: SEMANTIC.success,
  DEGRADED: SEMANTIC.warning,
  UNAVAILABLE: SEMANTIC.danger,
  UNKNOWN: NEUTRAL[400],
  ONLINE: SEMANTIC.success,
  OFFLINE: NEUTRAL[400],
  MAINTENANCE: SEMANTIC.info,
  DECOMMISSIONED: NEUTRAL[400],

  // health / severity
  ON_TRACK: SEMANTIC.success,
  AT_RISK: SEMANTIC.warning,
  OFF_TRACK: SEMANTIC.danger,
  LOW: NEUTRAL[400],
  NORMAL: SEMANTIC.info,
  HIGH: SEMANTIC.warning,
  CRITICAL: SEMANTIC.danger,
  MINOR: NEUTRAL[400],
  MODERATE: SEMANTIC.info,
  MAJOR: SEMANTIC.warning,

  // log levels
  TRACE: NEUTRAL[400],
  DEBUG: NEUTRAL[400],
  INFO: SEMANTIC.info,
  WARNING: SEMANTIC.warning,
  WARN: SEMANTIC.warning,
  ERROR: SEMANTIC.danger,

  // audit results
  SUCCESS: SEMANTIC.success,
  FAILURE: SEMANTIC.danger,
  DENIED: SEMANTIC.warning,
};

export function statusColor(value: string | null | undefined): string {
  if (!value) return NEUTRAL[400];
  return STATUS_COLORS[value.toUpperCase()] ?? NEUTRAL[400];
}

/** The status colour only when there is one — `undefined` otherwise. */
export function knownStatusColor(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  return STATUS_COLORS[value.toUpperCase()];
}

/**
 * The colour a category should be drawn in.
 *
 * A known status keeps its own colour, so `DONE` is the same green on the
 * chart, in the table and on the board. Anything else takes the next series
 * colour rather than being painted the "unknown" grey — a bar chart of ticket
 * categories is not a chart of statuses, and rendering it entirely grey to
 * signal that would be a strange thing to do to the reader.
 */
export function categoryColor(value: string | null | undefined, index: number): string {
  return knownStatusColor(value) ?? SERIES[index % SERIES.length] ?? SERIES[0];
}

export const RADIUS = { control: 4, card: 6, modal: 8, pill: 999 } as const;

/** 4px base unit. Anything not on this scale is a mistake, not a nuance. */
export const SPACE = [0, 4, 8, 12, 16, 24, 32, 48] as const;

export const FONT = {
  family:
    "'Inter Variable', Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
  mono: "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
  sizes: { xs: 12, sm: 13, base: 14, md: 16, lg: 20, xl: 24, xxl: 30 },
} as const;

export type Density = "compact" | "middle" | "comfortable";

/**
 * The three density modes (§1, §40).
 *
 * `compact` fits about forty rows on a laptop screen, which is the point: an
 * operator scanning a queue wants the whole queue, not eight rows and a lot of
 * air.
 */
export const DENSITY: Record<
  Density,
  { rowHeight: number; controlHeight: number; fontSize: number; padding: number }
> = {
  compact: { rowHeight: 32, controlHeight: 28, fontSize: 13, padding: 8 },
  middle: { rowHeight: 40, controlHeight: 32, fontSize: 14, padding: 12 },
  comfortable: { rowHeight: 52, controlHeight: 40, fontSize: 14, padding: 16 },
};

export const LAYOUT = {
  headerHeight: 56,
  sidebarWidth: 240,
  sidebarCollapsedWidth: 64,
  contentMaxWidth: 1680,
  breakpoints: { mobile: 768, tablet: 1024, laptop: 1440 },
} as const;

/**
 * Fast enough to feel immediate, slow enough to be followed. Nothing that
 * happens on every keystroke gets a transition at all.
 */
export const MOTION = {
  fast: "120ms cubic-bezier(0.4, 0, 0.2, 1)",
  base: "180ms cubic-bezier(0.4, 0, 0.2, 1)",
  slow: "240ms cubic-bezier(0.4, 0, 0.2, 1)",
} as const;

export const SHADOW = {
  sm: "0 1px 2px rgba(15, 23, 42, 0.06)",
  md: "0 2px 8px rgba(15, 23, 42, 0.08)",
  lg: "0 8px 24px rgba(15, 23, 42, 0.12)",
  xl: "0 16px 48px rgba(15, 23, 42, 0.18)",
} as const;

/**
 * Shadows for dark mode.
 *
 * A translucent-navy shadow over a charcoal surface is invisible; depth in a
 * dark UI comes from a *darker* shadow, not a lighter one, so these are much
 * more opaque than their light counterparts.
 */
export const SHADOW_DARK = {
  sm: "0 1px 2px rgba(0, 0, 0, 0.5)",
  md: "0 4px 16px rgba(0, 0, 0, 0.5)",
  lg: "0 12px 34px rgba(0, 0, 0, 0.62)",
  xl: "0 20px 56px rgba(0, 0, 0, 0.7)",
} as const;
