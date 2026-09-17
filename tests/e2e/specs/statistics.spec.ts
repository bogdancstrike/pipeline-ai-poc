/**
 * Statistics: what it cost to produce the corpus.
 *
 * The dashboard answers "what is in it"; this answers "how is the pipeline
 * behaving". The assertions worth making from the browser are the ones about
 * *honesty*: mocked calls counted separately, latency as a median and a p95
 * rather than a mean alone, and an empty table that says which.
 */
import { test, expect } from "../fixtures";

test.beforeEach(async ({ page }) => {
  await page.goto("/statistics");
  await expect(page.getByRole("heading", { name: "Statistics" })).toBeVisible();
});

test("shows the four headline numbers", async ({ page }) => {
  const row = page.locator(".kpi-row");

  await expect(row).toContainText("AI calls");
  await expect(row).toContainText("Live / mocked");
  await expect(row).toContainText("Failure rate");
  await expect(row).toContainText("Tokens in / out");
});

test("counts live and mocked separately", async ({ page }) => {
  const tile = page.locator(".kpi-row .ant-card", { hasText: "Live / mocked" });
  await expect(tile).toContainText("/");
});

test("lists one row per service", async ({ page }) => {
  const table = page.locator(".stats-table");

  for (const service of [
    "face-match-main",
    "video-describe-354b",
    "transcribe",
    "video-ocr",
    "summary",
    "entities",
    "sentiment",
  ]) {
    await expect(table.getByRole("cell", { name: service, exact: true })).toBeVisible();
  }
});

test("reports a median and a p95, not only a mean", async ({ page }) => {
  const table = page.locator(".stats-table");

  await expect(table.getByRole("columnheader", { name: "Median" })).toBeVisible();
  await expect(table.getByRole("columnheader", { name: "p95" })).toBeVisible();
  await expect(table.getByRole("columnheader", { name: "Max" })).toBeVisible();
});

test("says how many of a service's calls were mocked", async ({ page }) => {
  await expect(page.locator(".stats-table")).toContainText("mocked");
});

test("draws calls and latency over time", async ({ page }) => {
  await expect(page.getByText("Calls and latency per day")).toBeVisible();
  await expect(page.locator('[role="img"]').first()).toBeVisible();
});

test("names the models that answered", async ({ page }) => {
  const models = page.locator(".ant-card", { hasText: "Models" });
  await expect(models.getByRole("cell", { name: "phi4:14b-q8_0" }).first()).toBeVisible();
});

test("lists recent failures, or says every call answered", async ({ page }) => {
  const card = page.locator(".ant-card", { hasText: "Recent failures" });
  await expect(card).toBeVisible();

  const empty = card.getByText("Every call in this window answered.");
  const rows = card.locator("tbody tr.ant-table-row");
  expect((await empty.count()) + (await rows.count())).toBeGreaterThan(0);
});

test("a failure names the video, the service and the error", async ({ page }) => {
  const card = page.locator(".ant-card", { hasText: "Recent failures" });
  const first = card.locator("tbody tr.ant-table-row").first();

  if (await first.count()) {
    const cells = await first.locator("td").allInnerTexts();
    expect(cells[0]).not.toBe("");
    expect(cells[1]).not.toBe("");
    expect(cells[2]).not.toBe("");
  }
});

test("the window can be changed and the numbers follow", async ({ page }) => {
  const request = page.waitForRequest((r) => r.url().includes("/client/statistics?range=last_7_days"));
  await page.getByLabel("Time range").getByText("7 days", { exact: true }).click();

  expect((await request).url()).toContain("last_7_days");
  await expect(page.locator(".stats-table")).toBeVisible();
});

test("every window renders without an error", async ({ page }) => {
  for (const label of ["7 days", "30 days", "90 days", "This month", "This year"]) {
    await page.getByLabel("Time range").getByText(label, { exact: true }).click();
    await expect(page.getByText("The statistics could not be built")).toHaveCount(0);
    await expect(page.locator(".kpi-row").first()).toBeVisible();
  }
});
