/**
 * The same screens on a phone.
 *
 * Runs under the `mobile` project only. A dashboard that needs a 1440px window
 * is a dashboard nobody checks from a train, and the failure mode is silent:
 * the page renders, and the reader scrolls sideways for ever.
 */
import { test, expect } from "../fixtures";

test("the dashboard fits the width", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(2);
});

test("the KPI tiles stack instead of squeezing", async ({ page }) => {
  await page.goto("/");
  const tiles = page.locator(".kpi-row .ant-card");
  await expect(tiles.first()).toBeVisible();

  const first = await tiles.first().boundingBox();
  const second = await tiles.nth(1).boundingBox();
  expect(second!.y).toBeGreaterThan(first!.y);
});

test("the records table is reachable and scrolls inside itself", async ({ page }) => {
  await page.goto("/records?q=qa-");
  await expect(page.locator("tr.ant-table-row").first()).toBeVisible();

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(2);
});

test("a record can be opened on a phone", async ({ page }) => {
  await page.goto("/records?q=qa-");
  await page.locator("tr.ant-table-row").first().locator(".cell-video a").click();

  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("dialog").getByText("Face match")).toBeVisible();
});

test("the statistics page fits", async ({ page }) => {
  await page.goto("/statistics");
  await expect(page.getByRole("heading", { name: "Statistics" })).toBeVisible();

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(2);
});

test("the pipeline page fits", async ({ page }) => {
  await page.goto("/pipeline");
  await expect(page.getByRole("heading", { name: "Pipeline" })).toBeVisible();

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(2);
});

test("the menu can still be reached", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("menuitem", { name: "Records" })).toBeVisible();
  await page.getByRole("menuitem", { name: "Records" }).click();
  await expect(page).toHaveURL(/\/records/);
});
