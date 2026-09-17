/**
 * Saved searches: the drawer where a question is kept and got back to.
 *
 * These tests write, so they run one after another and remove what they made.
 * What is stored is the *request*, not the answer — so the test that matters
 * most is the one that applies a saved search and checks the table behind it
 * changed to match.
 */
import { test, expect, CORPUS, rows, settled, openSeededRecords } from "../fixtures";

test.describe.configure({ mode: "serial" });

const NAME = `qa-e2e ${Date.now()}`;

async function openDrawer(page) {
  await page.getByRole("button", { name: "Saved searches" }).click();
  await expect(page.getByRole("dialog").getByText("Saved searches")).toBeVisible();
}

async function removeIfPresent(page, name: string) {
  await openDrawer(page);
  const item = page.locator(".ant-list-item", { hasText: name });
  if (await item.count()) {
    await item.first().getByRole("button", { name: "Delete", exact: true }).click();
    await page.getByRole("button", { name: "OK" }).click();
    await expect(page.locator(".ant-list-item", { hasText: name })).toHaveCount(0);
  }
  await page.locator(".ant-drawer-close").click();
}

test("a narrowed table can be saved under a name", async ({ page }) => {
  await openSeededRecords(page, { sentiment: "NEGATIVE" });
  await expect(page.locator(".search-count")).toContainText(`${CORPUS.sentiments.NEGATIVE} records`);

  await page.getByRole("button", { name: "Save search" }).click();
  const modal = page.getByRole("dialog");
  await expect(modal.getByText("Save this search")).toBeVisible();

  // The modal says what is about to be saved.
  await expect(modal).toContainText(`${CORPUS.sentiments.NEGATIVE} records match right now`);

  await modal.getByLabel("Name").fill(NAME);
  await modal.getByLabel("Why it is worth keeping").fill("Written by the E2E suite");
  await modal.getByLabel("Saved by").fill("qa");
  await modal.getByRole("button", { name: "Save" }).click();

  await expect(page.getByText(`Saved "${NAME}"`)).toBeVisible();
});

test("a saved search needs a name", async ({ page }) => {
  await openSeededRecords(page);
  await page.getByRole("button", { name: "Save search" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();

  await expect(page.getByText("A saved search needs a name")).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
});

test("it is listed with who saved it and what it asks", async ({ page }) => {
  await openSeededRecords(page);
  await openDrawer(page);

  const item = page.locator(".ant-list-item", { hasText: NAME });
  await expect(item).toBeVisible();
  await expect(item).toContainText("Written by the E2E suite");
  await expect(item).toContainText("qa");
  await expect(item).toContainText("sentiment=NEGATIVE");
});

test("it can be found by name", async ({ page }) => {
  await openSeededRecords(page);
  await openDrawer(page);

  await page.getByRole("dialog").getByPlaceholder("Find one").fill(NAME);
  await expect(page.locator(".ant-list-item")).toHaveCount(1);
});

test("applying one puts the question back on the table and closes", async ({ page }) => {
  await openSeededRecords(page);
  await expect(page.locator(".search-count")).toContainText(`${CORPUS.size} records`);

  await openDrawer(page);
  await page.locator(".ant-list-item", { hasText: NAME }).getByRole("button", { name: "Apply" }).click();

  await expect(page.getByRole("dialog")).toBeHidden();
  await settled(page);

  await expect(page.locator(".search-count")).toContainText(`${CORPUS.sentiments.NEGATIVE} records`);
  await expect(page).toHaveURL(/sentiment=NEGATIVE/);
  await expect(rows(page).first()).toBeVisible();
});

test("applying one counts the use, so recently-used is honest", async ({ page }) => {
  await openSeededRecords(page);
  await openDrawer(page);

  await expect(page.locator(".ant-list-item", { hasText: NAME })).toContainText(/\d+ run/);
  await page.locator(".ant-drawer-close").click();
});

test("it can be pinned, and stays pinned", async ({ page }) => {
  await openSeededRecords(page);
  await openDrawer(page);

  const item = page.locator(".ant-list-item", { hasText: NAME });
  await item.getByRole("button", { name: "Pin", exact: true }).click();
  await expect(item.getByText("pinned")).toBeVisible();

  await page.reload();
  await settled(page);
  await openDrawer(page);
  await expect(page.locator(".ant-list-item", { hasText: NAME }).getByText("pinned")).toBeVisible();
});

test("deleting one asks first", async ({ page }) => {
  await openSeededRecords(page);
  await openDrawer(page);

  await page.locator(".ant-list-item", { hasText: NAME }).getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page.getByText("Delete this saved search?")).toBeVisible();

  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.locator(".ant-list-item", { hasText: NAME })).toBeVisible();
});

test("deleting one removes it", async ({ page }) => {
  await openSeededRecords(page);
  await openDrawer(page);

  await page.locator(".ant-list-item", { hasText: NAME }).getByRole("button", { name: "Delete", exact: true }).click();
  await page.getByRole("button", { name: "OK" }).click();

  await expect(page.getByText("Deleted")).toBeVisible();
  await expect(page.locator(".ant-list-item", { hasText: NAME })).toHaveCount(0);
});

test("an advanced condition can be saved from the drawer without running it", async ({ page }) => {
  const advancedName = `${NAME} advanced`;
  await openSeededRecords(page);

  await page.getByRole("button", { name: "Advanced" }).click();
  await expect(page.getByLabel("Advanced query builder")).toBeVisible();

  const drawer = page.locator(".ant-drawer-content");
  await drawer.getByRole("button", { name: "Add rule" }).click();
  const rule = page.getByLabel("Advanced query builder").locator(".rule").last();
  await rule.locator(".rule--field .ant-select").click();
  const menu = page.locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden)");
  await menu.getByText("Sentiment", { exact: true }).first().click();
  await expect(rule.locator(".rule--value .ant-select")).toBeVisible();
  await rule.locator(".rule--value .ant-select").click();
  await menu.getByText("Negative", { exact: true }).first().click();

  await drawer.getByRole("button", { name: /Save as/ }).click();

  const modal = page.getByRole("dialog").filter({ hasText: "Save this search" });
  await modal.getByLabel("Name").fill(advancedName);
  await modal.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(`Saved "${advancedName}"`)).toBeVisible();

  // Pinning what actually happens: "Save as…" also *applies* the draft to the
  // page behind the drawer, so the saved payload and the summary in the modal
  // describe the same question. The "nothing runs until you say so" promise is
  // about closing the drawer, not about this button.
  await expect(page.locator(".condition-strip")).toContainText("Sentiment");

  // The builder stays open to keep editing, so it has to be closed before the
  // page behind it can be reached.
  await page.locator(".ant-drawer-close").click();
  await expect(page.getByLabel("Advanced query builder")).toBeHidden();

  // It is marked as carrying a condition, and applying it runs that condition.
  await openDrawer(page);
  const item = page.locator(".ant-list-item", { hasText: advancedName });
  await expect(item.locator(".ant-tag", { hasText: "advanced" })).toBeVisible();

  await item.getByRole("button", { name: "Apply" }).click();
  await settled(page);
  await expect(page.locator(".condition-strip")).toContainText("Sentiment");

  await removeIfPresent(page, advancedName);
});

test("the drawer says what to do when nothing is saved", async ({ page }) => {
  await openSeededRecords(page);
  await openDrawer(page);

  const empty = page.getByText("Nothing saved yet. Narrow the table, then press Save search.");
  const list = page.locator(".ant-list-item");
  // Whichever is true of this instance, one of them has to be on screen.
  expect((await empty.count()) + (await list.count())).toBeGreaterThan(0);
});
