/**
 * The dashboard: five tiles, six charts, and the drill-downs that make a chart
 * worth clicking.
 *
 * ECharts draws to a canvas, so what can be asserted about a chart from the
 * outside is that it rendered, that it is labelled for a screen reader, and
 * that its empty state says *why* it is empty. The numbers themselves are
 * checked against the corpus in the integration suite, where they can be.
 */
import { test, expect } from "../fixtures";

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
});

test.describe("the KPI row", () => {
  test("shows five tiles", async ({ page }) => {
    await expect(page.locator(".kpi-row .ant-card")).toHaveCount(5);
  });

  test("every tile carries a label and a number", async ({ page }) => {
    const tiles = page.locator(".kpi-row .ant-card");

    for (let index = 0; index < 5; index += 1) {
      const tile = tiles.nth(index);
      await expect(tile).toBeVisible();
      await expect(tile).not.toHaveText("");
    }
  });

  test("the tiles name the things the pipeline produces", async ({ page }) => {
    const row = page.locator(".kpi-row");
    await expect(row).toContainText("Videos analysed");
    await expect(row).toContainText("Entities extracted");
    await expect(row).toContainText("Person matches");
  });
});

test.describe("the charts", () => {
  test("all six are drawn", async ({ page }) => {
    for (const title of [
      "Videos analysed",
      "Sentiment",
      "Entities by type",
      "Most-mentioned entities",
      "People most often matched",
      "Average call time per service",
    ]) {
      await expect(page.getByText(title, { exact: true }).first()).toBeVisible();
    }
  });

  test("each chart is labelled for a reader who cannot see it", async ({ page }) => {
    const charts = page.locator('[role="img"]');
    await expect(charts.first()).toBeVisible();
    expect(await charts.count()).toBeGreaterThanOrEqual(4);

    for (let index = 0; index < (await charts.count()); index += 1) {
      await expect(charts.nth(index)).toHaveAttribute("aria-label", /.+/);
    }
  });

  test("a chart with nothing in it says why rather than drawing an empty box", async ({ page }) => {
    // With every worker mocked, the latency chart has nothing live to average.
    const card = page.locator(".ant-card", { hasText: "Average call time per service" });
    await expect(card).toBeVisible();
  });
});

test.describe("the time range", () => {
  /**
   * A Segmented control, and the labels are short: what matters is that every
   * one of the five the picker offers is a preset the server actually resolves.
   * A UI window the API silently widens to its default is a number nobody can
   * reconcile.
   */
  const RANGES = ["7 days", "30 days", "90 days", "This month", "This year"];

  test("offers the five windows the API resolves", async ({ page }) => {
    const picker = page.getByLabel("Time range");

    for (const label of RANGES) {
      await expect(picker.getByText(label, { exact: true })).toBeVisible();
    }
  });

  test("changing it asks the server again", async ({ page }) => {
    const request = page.waitForRequest((r) => r.url().includes("/client/dashboard?range=last_7_days"));
    await page.getByLabel("Time range").getByText("7 days", { exact: true }).click();

    await expect(page.locator(".kpi-row .ant-card").first()).toBeVisible();
    expect((await request).url()).toContain("last_7_days");
  });

  test("every window renders numbers rather than a spinner that stays", async ({ page }) => {
    for (const label of RANGES) {
      await page.getByLabel("Time range").getByText(label, { exact: true }).click();
      await expect(page.locator(".kpi-row .ant-card").first()).toBeVisible();
      await expect(page.locator(".ant-skeleton")).toHaveCount(0);
      await expect(page.getByText("The dashboard could not be built")).toHaveCount(0);
    }
  });

  test("a narrower window cannot report more videos than a wider one", async ({ page }) => {
    const analysed = () =>
      page
        .locator(".kpi-row .ant-card", { hasText: "Videos analysed" })
        .locator(".ant-statistic-content-value, .kpi-value")
        .first()
        .innerText();

    await page.getByLabel("Time range").getByText("90 days", { exact: true }).click();
    await expect(page.locator(".ant-skeleton")).toHaveCount(0);
    const wide = Number((await analysed()).replace(/[^0-9]/g, ""));

    await page.getByLabel("Time range").getByText("7 days", { exact: true }).click();
    await expect(page.locator(".ant-skeleton")).toHaveCount(0);
    const narrow = Number((await analysed()).replace(/[^0-9]/g, ""));

    expect(narrow).toBeLessThanOrEqual(wide);
  });
});

test.describe("drilling into the records", () => {
  test("the partial-records link opens the explorer already narrowed", async ({ page }) => {
    await page.getByRole("link", { name: "Show partial records" }).click();

    await expect(page).toHaveURL(/\/records\?status=partial/);
    await expect(page.getByRole("heading", { name: "Records" })).toBeVisible();
    await expect(
      page.getByText("Showing only records where at least one service did not answer."),
    ).toBeVisible();
  });

  test("the reader is told the charts can be clicked", async ({ page }) => {
    await expect(page.getByText("Charts are clickable")).toBeVisible();
  });
});
