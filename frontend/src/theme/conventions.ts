/**
 * The rules a control on a page follows, declared once (§60).
 *
 * A platform that looks designed and a platform that looks assembled differ in
 * almost nothing a screenshot can show. What separates them is whether the same
 * decision is made the same way twice — and this file is where those decisions
 * are written down, so "which button is this" has an answer somebody can look
 * up rather than infer from whichever page they opened last.
 *
 * `conventions.test.ts` asserts every rule here against the shipped source, so
 * a page that drifts fails the suite rather than the eye. That is the whole
 * point of declaring them: a style guide nothing checks is a document, and a
 * document is what the drift happened underneath.
 *
 * ── The four roles a button can play ─────────────────────────────────────
 *
 * Every button in this product is one of four things, and the spelling is
 * fixed so a reader learns each one once:
 *
 * | Role         | Spelling                        | Where |
 * | ------------ | ------------------------------- | ----- |
 * | Primary      | `type="primary"`                | The page's one main verb, in the header |
 * | Secondary    | no `type`                       | Other verbs beside it |
 * | Quiet        | `type="text"`                   | Row actions, toolbar glyphs, anything repeated per row |
 * | Destructive  | `danger`, plus a confirm        | Anything that cannot be taken back (see `lib/confirm`) |
 *
 * **There is no fifth.** `type="link"` looks like a link and is not one: it
 * does not open in a new tab, a middle-click does nothing, and a screen reader
 * announces a button. Navigation is a `<Link>`; a quiet *action* is
 * `type="text"`. Having both spellings of "quiet" is how one page ends up with
 * two greys.
 *
 * **`type="dashed"` is unused on purpose.** It reads as "add another one of
 * these" and this product says that with a `+` and a word.
 *
 * ── Size belongs to the reader, not to the page ──────────────────────────
 *
 * `AppearanceProvider` maps the density preference onto AntD's
 * `componentSize`, so every control already answers to the three densities a
 * reader may choose. A page that writes `size="small"` overrides that choice —
 * and somebody who set the platform to *comfortable* because they cannot see
 * the compact one gets a page that ignores them.
 *
 * So: **pages never set a size.** A *shared component* may, because some are
 * structurally dense — a card tile is 190 pixels tall whatever the reader
 * prefers — and when one does, it says why in a comment. The boundary is the
 * point: judgement lives in the component that owns the constraint, not in the
 * forty pages that use it.
 *
 * ── A control that shows only an icon says its name ──────────────────────
 *
 * An icon-only button announces itself as "button" and nothing else. Every one
 * of them carries an `aria-label`, and the label is the *verb with its object*
 * — "Remove Open tickets", not "Remove" — because a screen reader reading down
 * a table of twelve rows otherwise hears the same word twelve times.
 *
 * ── One primary per surface ──────────────────────────────────────────────
 *
 * A page header, a drawer and a modal are three surfaces and each may have one
 * primary. Two primaries side by side is a page that has not decided what it
 * is for, and the reader pays for the indecision by reading both.
 */

/** The button roles, as the product spells them. */
export const BUTTON_ROLES = {
  /** The page's one main verb. */
  primary: { type: "primary" as const, when: "The single thing this surface is for." },
  /** Everything else with a word on it. */
  secondary: { type: undefined, when: "Other verbs beside the primary one." },
  /** Repeated, or subordinate: row actions and toolbar glyphs. */
  quiet: { type: "text" as const, when: "Anything repeated per row, or a glyph in a toolbar." },
  /** Cannot be taken back. Always paired with a confirmation (§73). */
  destructive: { danger: true, when: "Delete, remove, revoke — with a confirm behind it." },
} as const;

/**
 * Button types this product does not use, and what to write instead.
 *
 * Keyed by the AntD value so the test's message can name the replacement
 * rather than only the offence.
 */
export const FORBIDDEN_BUTTON_TYPES: Record<string, string> = {
  link: 'navigation is a <Link>; a quiet action is type="text"',
  dashed: 'this product says "add another" with a + and a word',
};

/**
 * Files allowed to set a control's size, and the constraint that earns it.
 *
 * Every entry is a *shared component* with a structural reason — not a page,
 * and not a preference. A file added here without a reason is a file that has
 * opted its readers out of their own density setting.
 */
export const DENSE_BY_CONSTRUCTION: Record<string, string> = {
  "components/ChartCard.tsx":
    "A chart card's toolbar, which shares a row with the chart's title.",
  "components/EmptyState.tsx":
    "The one control inside an empty state, sized to sit under a sentence rather than beside a heading.",
  "components/FailureAlert.tsx":
    "A retry inside an AntD Alert, which sizes its own action slot.",
  "components/announcements/AnnouncementBanner.tsx":
    "A banner is one line tall and spans the page.",
  "components/audit/AuditTimeline.tsx":
    "One control per timeline entry, repeated down the trail.",
  "components/automations/ActionListEditor.tsx":
    "Rows of one action each, each with its own controls.",
  "components/comments/CommentThread.tsx":
    "Reply and edit under each comment, repeated down a thread.",
  "components/dashboards/DashboardCard.tsx":
    "A gallery card's footer, where the controls sit under two lines of description.",
  "components/dashboards/WidgetCard.tsx":
    "A widget is a fixed number of grid rows, and its controls sit inside the heading they share with the title.",
  "components/dashboards/WidgetKindPicker.tsx":
    "A plus and a minus inside a 104-pixel tile, either side of a count.",
  "components/explorer/AdvancedQueryBuilder.tsx":
    "The library draws its own controls at `renderSize`; a differently sized one beside them is what reads as broken.",
  "components/explorer/ExplorerResults.tsx":
    "Row actions inside a table cell, repeated once per row.",
  "components/explorer/ExplorerSearch.tsx":
    "A control inside a search field's own affix.",
  "components/explorer/SavedSearchDrawer.tsx":
    "Card footers inside a 420-pixel drawer.",
  "components/explorer/SimpleSearch.tsx":
    "A control inside a search field's own affix.",
  "components/files/FilePreview.tsx":
    "Actions inside a preview pane's own toolbar.",
  "components/kanban/LaneColumn.tsx":
    "A lane header occupies the space a card's title needs, and the board is read by scanning columns.",
  "components/notifications/NotificationBell.tsx":
    "A popover list of notifications, each one row.",
  "components/records/useBulk.tsx":
    "The bulk bar renders inside a table's own header row, beside controls the table sized.",
  "components/records/useRecordPage.tsx":
    "Actions inside a record's own section headers.",
  "components/relationships/ConnectionMapView.tsx":
    "Controls overlaid on a canvas, which the picture has to stay visible behind.",
  "components/relationships/NetworkView.tsx":
    "Controls overlaid on a canvas, which the picture has to stay visible behind.",
};

/**
 * One empty state, and why AntD's is not it.
 *
 * There were three on screen at once: AntD's default illustration — the grey
 * cartoon box every React admin panel in the world ships with — its
 * `PRESENTED_IMAGE_SIMPLE` outline, and this product's own `EmptyState`. A
 * reader meeting all three in one session is not meeting a design.
 *
 * `EmptyState` also says something neither AntD variant can: §34's distinction
 * between *nothing yet*, which wants the control that makes the first record,
 * and *nothing matched*, which wants the filters cleared. A single shrug for
 * both leaves somebody unsure whether the system is empty or their filter is.
 *
 * `compact` is the in-a-card form; the full one is for a page's own body.
 */
export const EMPTY_STATE = {
  use: "EmptyState, or NoResults when a filter is the reason",
  not: "AntD's <Empty> — three illustrations in one product is not a design",
  owner: "components/EmptyState.tsx",
} as const;

/** Where a page's own controls live, so two pages do not invent two toolbars. */
export const ACTION_PLACEMENT = {
  page: "PageHeader's `actions` — one primary, then secondary verbs, then quiet glyphs.",
  row: 'Inside the row, `type="text"`, icon-only, with the verb and its object as the label.',
  surface: "A drawer or a modal owns its own primary, in `extra` or `okText`.",
} as const;
