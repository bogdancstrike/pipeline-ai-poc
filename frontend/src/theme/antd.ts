/**
 * The AntD theme, derived from `tokens.ts`.
 *
 * Nothing here invents a value. Every number and colour comes from the token
 * file, so re-theming the platform is one edit rather than a search for hex
 * codes across a hundred components.
 */

import { theme, type ThemeConfig } from "antd";

import {
  ACCENT,
  AVATAR_GROUND,
  DENSITY,
  FONT,
  INK,
  NEUTRAL,
  PAPER,
  RADIUS,
  SEMANTIC,
  SEMANTIC_INK,
  SHADOW,
  SHADOW_DARK,
  type Density,
} from "./tokens";

export type Appearance = "light" | "dark" | "system";

export function resolveAppearance(appearance: Appearance): "light" | "dark" {
  if (appearance !== "system") return appearance;
  // Server-side rendering has no window, and jsdom has no matchMedia; the DOM
  // types account for neither.
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
  if (typeof window === "undefined" || !window.matchMedia) return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function buildTheme(appearance: Appearance, density: Density): ThemeConfig {
  const mode = resolveAppearance(appearance);
  const scale = DENSITY[density];
  const dark = mode === "dark";

  return {
    algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      // Lighter in dark mode: #5b5bd6 on charcoal is legible but heavy, and
      // an accent that has to be hunted for stops being an accent.
      colorPrimary: dark ? ACCENT[400] : ACCENT[500],
      // Links are the accent itself, not the tint AntD derives from it.
      // The derived value (#6666d4) measures 4.47:1 against the off-white a
      // drawer body paints — just under the 4.5:1 body-text threshold (§55),
      // which axe reports as a serious violation on the record preview. The
      // token itself is 5.05:1 there and 5.37:1 on white.
      colorLink: dark ? ACCENT[300] : ACCENT[500],
      colorLinkHover: dark ? ACCENT[200] : ACCENT[600],
      colorLinkActive: dark ? ACCENT[400] : ACCENT[700],
      colorInfo: SEMANTIC.info,
      colorSuccess: SEMANTIC.success,
      colorWarning: SEMANTIC.warning,
      colorError: SEMANTIC.danger,

      colorBgLayout: dark ? INK[900] : NEUTRAL[100],
      colorBgContainer: dark ? INK[800] : PAPER,
      colorBgElevated: dark ? INK[750] : PAPER,
      colorBorder: dark ? INK[600] : NEUTRAL[200],
      colorBorderSecondary: dark ? INK[650] : NEUTRAL[100],
      colorText: dark ? INK[100] : NEUTRAL[900],
      colorTextSecondary: dark ? INK[300] : NEUTRAL[600],
      colorTextTertiary: dark ? INK[400] : NEUTRAL[500],
      // Named rather than left to AntD's derivation, which lands on
      // `NEUTRAL[500]` — 4.34:1 against the page background, just under the
      // bar. `Typography type="secondary"` is the most-used text style in the
      // product, so being a tenth of a point short of legible there is short
      // everywhere at once (§55).
      colorTextDescription: dark ? INK[300] : NEUTRAL[600],
      // The ink of every placeholder in the product — a Select with nothing
      // chosen, an empty search box, a date that has not been picked. AntD's
      // default is `#bfbfbf`, which is **1.83:1** on white: the lowest score
      // anywhere in this application, and it went unseen because no single
      // page's audit is about a placeholder. Found by auditing every route at
      // once. The tertiary ink is the quietest one measured (§55).
      colorTextPlaceholder: dark ? INK[400] : NEUTRAL[500],

      // Text on a *tinted* semantic ground — an `Alert type="error"`, a
      // `Typography.Text type="warning"`. AntD derives these from the fill,
      // which is tuned for a fill: amber on its own pale amber is 2.82:1, and
      // the labels that fail worst are the ones a reader most needs (§55).
      //
      // AntD's *preset-coloured tags* take their text from the base
      // `colorWarning` rather than from this, so they are named in the
      // stylesheet instead — see `.ant-tag-warning` in `index.css`.
      colorSuccessText: SEMANTIC_INK[mode].success,
      colorWarningText: SEMANTIC_INK[mode].warning,
      colorErrorText: SEMANTIC_INK[mode].danger,
      colorInfoText: SEMANTIC_INK[mode].info,

      fontFamily: FONT.family,
      fontFamilyCode: FONT.mono,
      fontSize: scale.fontSize,

      borderRadius: RADIUS.control,
      borderRadiusLG: RADIUS.card,
      borderRadiusSM: RADIUS.control,

      controlHeight: scale.controlHeight,

      boxShadow: dark ? SHADOW_DARK.md : SHADOW.md,
      boxShadowSecondary: dark ? SHADOW_DARK.lg : SHADOW.lg,

      // AntD's defaults are tuned for consumer apps. This is an operational
      // tool: less air, more rows.
      lineHeight: 1.5,
      wireframe: false,
    },
    components: {
      Layout: {
        headerBg: dark ? INK[850] : PAPER,
        headerHeight: 56,
        headerPadding: "0 16px",
        siderBg: dark ? INK[850] : PAPER,
        bodyBg: dark ? INK[900] : NEUTRAL[100],
      },
      Menu: {
        itemHeight: scale.controlHeight + 4,
        itemMarginInline: 8,
        itemBorderRadius: RADIUS.control,
        subMenuItemBg: "transparent",
      },
      Table: {
        cellPaddingBlock: (scale.rowHeight - scale.fontSize * 1.5) / 2,
        cellPaddingInline: scale.padding,
        headerBg: dark ? INK[750] : NEUTRAL[50],
        headerSplitColor: "transparent",
        rowHoverBg: dark ? INK[700] : ACCENT[50],
        borderColor: dark ? INK[650] : NEUTRAL[200],
      },
      Button: {
        // Two colours the dark algorithm derives to just under legible, which
        // is worth naming because these are the two buttons on every record
        // page (§55).
        //
        // A solid primary is white on the derived indigo `#6c6cd3` — 4.45:1,
        // a hundredth under the bar. The accent one step darker carries the
        // same white at 5.37:1 and reads as the same button.
        colorPrimary: dark ? ACCENT[500] : ACCENT[500],
        // The *fill* of a solid danger button, in both appearances.
        //
        // This was the dark ink (`#f87171`) to fix the outlined button's
        // label, which was the derived `#be2323` at 2.94:1 on a charcoal
        // panel — a Delete nobody can read. But one token was carrying two
        // roles: AntD also paints `type="primary" danger` with it and writes
        // **white** on top, and white on a light red is 2.76:1. So every
        // solid Delete in the dark appearance was illegible — including the
        // OK button of every delete confirmation in the product, which no
        // axe test had opened in dark until the bulk dialog.
        //
        // The fill stays fill-strength here (white on `#dc2626` is 4.83:1),
        // and the outlined button's *ink* is named in the stylesheet instead —
        // `.ant-btn-dangerous:not(.ant-btn-primary)` in `index.css`, the same
        // way the preset tags are. Asserted in `contrast.test.ts`.
        colorError: SEMANTIC.danger,
      },
      // An initials avatar's default ground is `#bfbfbf`, which carries white
      // text at 1.84:1 — every avatar in the product without a photograph was
      // illegible, and axe only found it on the first page that shows a column
      // of them. Slate at 7.6:1 (§55, §64), asserted in `contrast.test.ts`.
      Avatar: { colorTextPlaceholder: AVATAR_GROUND },
      Card: { paddingLG: scale.padding + 4 },
      Descriptions: { itemPaddingBottom: scale.padding },
      Tabs: {
        horizontalMargin: "0 0 12px 0",
        // The selected tab is named explicitly rather than left to the dark
        // algorithm's derivation, which lands on #6c6cd3 — 3.75:1 against a
        // charcoal panel, under the 4.5:1 body-text threshold at 13px (§55).
        // Named, it is 6.5:1 in dark and 5.4:1 in light.
        itemSelectedColor: dark ? ACCENT[300] : ACCENT[500],
        itemHoverColor: dark ? ACCENT[200] : ACCENT[600],
        inkBarColor: dark ? ACCENT[300] : ACCENT[500],
      },
      Tooltip: { colorBgSpotlight: dark ? INK[700] : NEUTRAL[800] },
      Modal: { borderRadiusLG: RADIUS.modal },
      Drawer: { paddingLG: 16 },
    },
  };
}

/**
 * The tokens the stylesheet needs as CSS custom properties.
 *
 * Anything styled outside an AntD component — the shell, the command palette,
 * a chart container — reads these, so it cannot drift from the component theme.
 */
export function cssVariables(appearance: Appearance, density: Density): Record<string, string> {
  const mode = resolveAppearance(appearance);
  const scale = DENSITY[density];
  const dark = mode === "dark";

  return {
    "--nu-accent": dark ? ACCENT[400] : ACCENT[500],
    // The readable half of the accent, for *text* — the same split `SEMANTIC`
    // and `SEMANTIC_INK` have, and for the same reason. The accent as a fill
    // is `#7c7cf5` in dark, which is 5.17:1 on a card and **4.21:1 on the
    // accent-soft tint** an unread row is painted with. A link inside a
    // highlighted row is precisely where accent text appears, so the one
    // ground it has to survive is the one it failed on (§55).
    "--nu-accent-ink": dark ? ACCENT[300] : ACCENT[700],
    "--nu-accent-soft": dark ? "rgba(124, 124, 245, 0.16)" : ACCENT[50],
    "--nu-bg": dark ? INK[900] : NEUTRAL[100],
    "--nu-surface": dark ? INK[800] : PAPER,
    "--nu-surface-raised": dark ? INK[750] : PAPER,
    "--nu-border": dark ? INK[650] : NEUTRAL[200],
    "--nu-border-subtle": dark ? INK[700] : NEUTRAL[100],
    "--nu-text": dark ? INK[100] : NEUTRAL[900],
    "--nu-text-secondary": dark ? INK[300] : NEUTRAL[600],
    "--nu-text-tertiary": dark ? INK[400] : NEUTRAL[500],
    "--nu-success": SEMANTIC.success,
    "--nu-warning": SEMANTIC.warning,
    "--nu-danger": SEMANTIC.danger,
    "--nu-info": SEMANTIC.info,
    // The readable half of the same four meanings, for text rather than fills
    // — see `SEMANTIC_INK`. Published as variables because the pages that need
    // them are styled in CSS, and a component resolving the theme in
    // JavaScript to pick a hex is a second place the mode can be got wrong.
    "--nu-success-ink": SEMANTIC_INK[mode].success,
    "--nu-warning-ink": SEMANTIC_INK[mode].warning,
    "--nu-danger-ink": SEMANTIC_INK[mode].danger,
    "--nu-info-ink": SEMANTIC_INK[mode].info,
    "--nu-row-height": `${scale.rowHeight}px`,
    "--nu-control-height": `${scale.controlHeight}px`,
    "--nu-font-size": `${scale.fontSize}px`,
    "--nu-padding": `${scale.padding}px`,
    "--nu-font": FONT.family,
    "--nu-font-mono": FONT.mono,
    // The radii AntD already applies to its own components, published so a
    // hand-built surface (the notification panel, a popover of our own) rounds
    // to the same corner rather than to whichever value somebody typed.
    "--nu-radius-control": `${RADIUS.control}px`,
    "--nu-radius-card": `${RADIUS.card}px`,
    "--nu-radius-modal": `${RADIUS.modal}px`,
    "--nu-shadow-sm": dark ? SHADOW_DARK.sm : SHADOW.sm,
    "--nu-shadow-md": dark ? SHADOW_DARK.md : SHADOW.md,
    "--nu-shadow-lg": dark ? SHADOW_DARK.lg : SHADOW.lg,
    // A hand-built surface needs the strong border too — the D3 graphs and the
    // notification rows draw with it.
    "--nu-border-strong": dark ? INK[600] : NEUTRAL[300],
    "--nu-hover": dark ? INK[700] : NEUTRAL[100],
  };
}
