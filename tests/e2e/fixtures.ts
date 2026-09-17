/**
 * What every spec needs: a page that fails loudly, and the corpus's own names.
 *
 * The `page` fixture is extended to fail a test on an uncaught exception or a
 * console error. That is not decoration — the bug this suite was written after
 * (`crypto.randomUUID is not a function`) was a console error and a blank
 * screen, and a test that only asserted "the heading is visible" on a page that
 * had already thrown would have passed.
 */
import { test as base, expect, type Page } from "@playwright/test";

/** Matches `tests/support/corpus.py`. */
export const CORPUS = {
  prefix: "qa-",
  size: 120,
  /** The id of the nth seeded record. */
  id: (index: number) => `qa-${String(index).padStart(4, "0")}`,
  name: (index: number) => `qa-${String(index).padStart(4, "0")}.mp4`,
  /** A phrase only record 7 carries, for the free-text box. */
  uniquePhrase: "Record 7:",
  sentiments: { NEGATIVE: 40, POSITIVE: 40, NEUTRAL: 40 },
  partial: 20,
} as const;

/** Console messages a healthy page is allowed to produce. */
const BENIGN = [
  /Download the React DevTools/i,
  /\[antd:/i, // AntD's own deprecation notices
  /findDOMNode is deprecated/i,
  /Support for defaultProps/i,
  /ResizeObserver loop/i,
];

export const test = base.extend<{ page: Page; expectedConsoleErrors: RegExp[] }>({
  /**
   * Patterns a *particular* test expects to see.
   *
   * Used with `test.use({ expectedConsoleErrors: [...] })` for the handful of
   * screens whose job is to render a failure: a 404 fetch is a console error
   * in every browser, and the page is correct precisely because it happened.
   */
  expectedConsoleErrors: [[], { option: true }],

  page: async ({ page, expectedConsoleErrors }, use) => {
    const problems: string[] = [];

    page.on("pageerror", (error) => problems.push(`uncaught: ${error.message}`));
    page.on("console", (message) => {
      if (message.type() !== "error") return;
      const text = message.text();
      if (BENIGN.some((pattern) => pattern.test(text))) return;
      if (expectedConsoleErrors.some((pattern) => pattern.test(text))) return;
      problems.push(`console.error: ${text}`);
    });

    await use(page);

    expect(problems, "the page reported errors while the test ran").toEqual([]);
  },
});

export { expect };

/**
 * The table's data rows.
 *
 * AntD renders a hidden `tr.ant-table-measure-row` first when a column is
 * fixed, so `tbody tr` is one more than the reader can see.
 */
export function rows(page: Page) {
  return page.locator("tr.ant-table-row");
}

/**
 * One of the three facet selects.
 *
 * `getByLabel` matches two nodes for an AntD Select — the root and its inner
 * input — so it is narrowed to the one that opens the menu.
 */
export function facet(page: Page, name: "sentiment" | "status" | "model") {
  return page.getByLabel(`Filter by ${name}`).first();
}

/** Wait for the table to have finished the request it is showing. */
export async function settled(page: Page) {
  await expect(page.locator(".search-count")).not.toHaveText(/Searching/, { timeout: 15_000 });
}

/** Narrow the explorer to the seeded corpus alone, via the URL the page reads. */
export async function openSeededRecords(page: Page, extra: Record<string, string> = {}) {
  const params = new URLSearchParams({ q: CORPUS.prefix, ...extra });
  await page.goto(`/records?${params.toString()}`);
  await settled(page);
}
