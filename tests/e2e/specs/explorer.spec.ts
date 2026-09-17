/**
 * The Records explorer: the whole job on one screen.
 *
 * Search, facets, paging, sorting, the record drawer and the permalink. The
 * corpus behind it is seeded and deterministic, so these assert *counts* where
 * a count is the thing that would be wrong.
 */
import { test, expect, CORPUS, facet, rows, settled, openSeededRecords } from "../fixtures";

test.describe("the results table", () => {
  test.beforeEach(async ({ page }) => {
    await openSeededRecords(page);
  });

  test("shows the seeded corpus and says how many there are", async ({ page }) => {
    await expect(page.locator(".search-count")).toContainText(`${CORPUS.size} records`);
  });

  test("a row names the video and previews its summary", async ({ page }) => {
    const first = rows(page).first();
    await expect(first.locator(".cell-video a")).toContainText(/qa-\d{4}\.mp4/);
    await expect(first.locator(".cell-preview")).not.toHaveText("");
  });

  test("the columns the API declares are the columns that are drawn", async ({ page }) => {
    const headings = await page.locator("thead th:not(.ant-table-measure-cell)").allInnerTexts();

    expect(headings).toEqual([
      "Video", "Analysed", "Sentiment", "Persons", "Entities", "Status", "Processing time (s)",
    ]);
  });

  test("the video's name is drawn once, not under two headings", async ({ page }) => {
    const headings = await page.locator("thead th:not(.ant-table-measure-cell)").allInnerTexts();
    expect(headings.filter((heading) => heading === "Video")).toHaveLength(1);
  });

  test("the footer counts the whole answer, not the page", async ({ page }) => {
    await expect(page.locator(".ant-pagination-total-text")).toContainText(`of ${CORPUS.size}`);
  });
});

test.describe("paging", () => {
  test.beforeEach(async ({ page }) => {
    await openSeededRecords(page);
  });

  test("the second page holds different records", async ({ page }) => {
    const firstRow = () => rows(page).first().locator(".cell-video a").innerText();
    const before = await firstRow();

    await page.getByTitle("Next Page").click();
    await settled(page);

    expect(await firstRow()).not.toBe(before);
  });

  test("the page travels in the URL, so it can be pasted", async ({ page }) => {
    await page.getByTitle("Next Page").click();
    await settled(page);
    await expect(page).toHaveURL(/page=2/);
  });

  test("the page size can be changed and the table follows", async ({ page }) => {
    await expect(rows(page)).toHaveCount(25);

    await page.locator(".ant-pagination-options .ant-select").click();
    await page.getByTitle("10 / page").click();
    await settled(page);

    await expect(rows(page)).toHaveCount(10);
    await expect(page).toHaveURL(/page_size=10/);
  });

  test("narrowing the search sends the reader back to page one", async ({ page }) => {
    await page.getByTitle("Next Page").click();
    await settled(page);
    await expect(page).toHaveURL(/page=2/);

    await page.getByLabel("Search every text field").fill(CORPUS.uniquePhrase);
    await settled(page);

    await expect(page).not.toHaveURL(/page=2/);
  });
});

test.describe("sorting", () => {
  test.beforeEach(async ({ page }) => {
    await openSeededRecords(page);
  });

  test("a sortable column sorts, and the database does it", async ({ page }) => {
    // Descending first, so the assertion cannot be satisfied by the default
    // order: the corpus is newest-first, which is also name-ascending.
    await page.getByRole("columnheader", { name: /Video/ }).click();
    await settled(page);
    await page.getByRole("columnheader", { name: /Video/ }).click();
    await settled(page);

    const names = await rows(page).locator(".cell-video a").allInnerTexts();
    expect(names).toEqual([...names].sort().reverse());
    // 25 of 120 rows, and the first is the last name in the whole corpus —
    // which only holds if the ordering happened in PostgreSQL.
    expect(names[0]).toBe(CORPUS.name(CORPUS.size - 1));
  });

  test("clicking again reverses it", async ({ page }) => {
    const header = page.getByRole("columnheader", { name: /Video/ });
    await header.click();
    await settled(page);
    await header.click();
    await settled(page);

    const names = await rows(page).locator(".cell-video a").allInnerTexts();
    expect(names).toEqual([...names].sort().reverse());
  });

  test("the sort travels in the URL", async ({ page }) => {
    await page.getByRole("columnheader", { name: /Video/ }).click();
    await settled(page);
    await expect(page).toHaveURL(/sort=name/);
  });
});

test.describe("the search bar", () => {
  test("free text narrows to the records that carry the term", async ({ page }) => {
    await openSeededRecords(page);

    await page.getByLabel("Search every text field").fill(CORPUS.uniquePhrase);
    await settled(page);

    await expect(page.locator(".search-count")).toContainText("1 record");
    await expect(rows(page)).toHaveCount(1);
  });

  test("the text is debounced rather than submitted", async ({ page }) => {
    await openSeededRecords(page);
    const box = page.getByLabel("Search every text field");

    await box.fill("Record");
    await box.fill("Record 7");
    await box.fill(CORPUS.uniquePhrase);
    await settled(page);

    await expect(page.locator(".search-count")).toContainText("1 record");
  });

  test("the term travels in the URL", async ({ page }) => {
    await openSeededRecords(page);
    await page.getByLabel("Search every text field").fill("breakwater");
    await settled(page);
    await expect(page).toHaveURL(/q=breakwater/);
  });

  test("a term nothing matches shows an empty table, not an error", async ({ page }) => {
    await openSeededRecords(page);
    await page.getByLabel("Search every text field").fill("zzzz-no-such-word");
    await settled(page);

    await expect(page.locator(".search-count")).toContainText("0 records");
    await expect(page.getByText("The search failed")).toHaveCount(0);
  });

  test("the sentiment menu is built from the data, with counts", async ({ page }) => {
    await openSeededRecords(page);
    await facet(page, "sentiment").click();

    await expect(page.getByTitle(`NEGATIVE (${CORPUS.sentiments.NEGATIVE})`)).toBeVisible();
    await expect(page.getByTitle(`POSITIVE (${CORPUS.sentiments.POSITIVE})`)).toBeVisible();
  });

  test("picking a sentiment narrows the table", async ({ page }) => {
    await openSeededRecords(page);
    await facet(page, "sentiment").click();
    await page.getByTitle(`NEGATIVE (${CORPUS.sentiments.NEGATIVE})`).click();
    await page.keyboard.press("Escape");
    await settled(page);

    await expect(page.locator(".search-count")).toContainText(
      `${CORPUS.sentiments.NEGATIVE} records`,
    );
    await expect(page).toHaveURL(/sentiment=NEGATIVE/);
  });

  test("the menu keeps offering the sentiments not yet chosen", async ({ page }) => {
    /**
     * Regression: the facet counts were computed from the fully filtered
     * question, so choosing one value removed every other option and the
     * multi-select could only ever hold one thing.
     */
    await openSeededRecords(page, { sentiment: "NEGATIVE" });

    await facet(page, "sentiment").click();
    const menu = page.locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden)");

    for (const value of ["NEGATIVE", "POSITIVE", "NEUTRAL"] as const) {
      // The chosen value also appears in the closed selector, hence the menu.
      await expect(menu.getByTitle(`${value} (${CORPUS.sentiments[value]})`)).toBeVisible();
    }
    await page.keyboard.press("Escape");
  });

  test("two sentiments widen it", async ({ page }) => {
    await openSeededRecords(page);

    await facet(page, "sentiment").click();
    await page.getByTitle(`NEGATIVE (${CORPUS.sentiments.NEGATIVE})`).click();
    await page.keyboard.press("Escape");
    await settled(page);
    await expect(page.locator(".search-count")).toContainText(
      `${CORPUS.sentiments.NEGATIVE} records`,
    );

    await facet(page, "sentiment").click();
    await page.getByTitle(`POSITIVE (${CORPUS.sentiments.POSITIVE})`).click();
    await page.keyboard.press("Escape");
    await settled(page);

    await expect(page.locator(".search-count")).toContainText(
      `${CORPUS.sentiments.NEGATIVE + CORPUS.sentiments.POSITIVE} records`,
    );
  });

  test("the status menu finds the partial records", async ({ page }) => {
    await openSeededRecords(page);
    await facet(page, "status").click();
    await page.getByTitle(`partial (${CORPUS.partial})`).click();
    await page.keyboard.press("Escape");
    await settled(page);

    await expect(page.locator(".search-count")).toContainText(`${CORPUS.partial} records`);
  });

  test("Clear appears once something is narrowed, and empties it", async ({ page }) => {
    await openSeededRecords(page, { sentiment: "NEGATIVE" });
    await expect(page.locator(".search-count")).toContainText(
      `${CORPUS.sentiments.NEGATIVE} records`,
    );

    await page.getByRole("button", { name: "Clear" }).click();
    await settled(page);

    await expect(page).not.toHaveURL(/sentiment=/);
  });

  test("a pasted URL is the search it describes", async ({ page }) => {
    await openSeededRecords(page, { sentiment: "NEUTRAL" });
    await expect(page.locator(".search-count")).toContainText(
      `${CORPUS.sentiments.NEUTRAL} records`,
    );
  });
});

test.describe("opening a record", () => {
  test("a row opens the drawer without leaving the list", async ({ page }) => {
    await openSeededRecords(page);
    await rows(page).locator(".cell-video a").first().click();

    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page).toHaveURL(/\/records\?/, { timeout: 5_000 });
  });

  test("the drawer shows everything the pipeline produced", async ({ page }) => {
    await openSeededRecords(page);
    await rows(page).locator(".cell-video a").first().click();
    const drawer = page.getByRole("dialog");

    await expect(drawer.getByText("Face match")).toBeVisible();
    await expect(drawer.getByText("Description", { exact: false }).first()).toBeVisible();
    await expect(drawer.getByText(/Transcript/).first()).toBeVisible();
    await expect(drawer.getByText(/On-screen text/)).toBeVisible();
    await expect(drawer.getByText("Summary", { exact: true })).toBeVisible();
    await expect(drawer.getByText(/Entities ·/)).toBeVisible();
  });

  test("the drawer names the service behind each panel", async ({ page }) => {
    await openSeededRecords(page);
    await rows(page).locator(".cell-video a").first().click();
    const drawer = page.getByRole("dialog");

    await expect(drawer.getByText(/face-match-main · :8821/)).toBeVisible();
    await expect(drawer.getByText(/transcribe · :8824/)).toBeVisible();
    await expect(drawer.getByText(/summarize · :8825 · summary\.txt/)).toBeVisible();
  });

  test("the drawer offers the calls and the raw record", async ({ page }) => {
    await openSeededRecords(page);
    await rows(page).locator(".cell-video a").first().click();
    const drawer = page.getByRole("dialog");

    await drawer.getByRole("tab", { name: /Calls/ }).click();
    await expect(drawer.getByRole("cell", { name: "face-match-main" })).toBeVisible();

    await drawer.getByRole("tab", { name: "JSON" }).click();
    await expect(drawer.locator(".record-json")).toContainText("enrichment");
  });

  test("the drawer closes and the list is where it was", async ({ page }) => {
    await openSeededRecords(page);
    const before = await rows(page).count();

    await rows(page).locator(".cell-video a").first().click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.locator(".ant-drawer-close").click();

    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(rows(page)).toHaveCount(before);
  });

  test("the drawer offers the permalink", async ({ page }) => {
    await openSeededRecords(page);
    await rows(page).locator(".cell-video a").first().click();

    await page.getByRole("link", { name: "Open as a page" }).click();
    await expect(page).toHaveURL(/\/records\/qa-\d{4}$/);
  });

  test("a partial record says which service did not answer", async ({ page }) => {
    await openSeededRecords(page, { status: "partial" });
    await rows(page).locator(".cell-video a").first().click();
    const drawer = page.getByRole("dialog");

    await expect(drawer.getByText(/service\(s\) did not answer/)).toBeVisible();
  });

  test("a video that is not mounted here says so instead of a black rectangle", async ({ page }) => {
    await openSeededRecords(page);
    await rows(page).locator(".cell-video a").first().click();

    await expect(
      page.getByRole("dialog").getByText("This video cannot be played here"),
    ).toBeVisible();
  });
});
