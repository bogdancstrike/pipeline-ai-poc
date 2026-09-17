/**
 * The frame every screen is drawn in, and the routes it can reach.
 *
 * These are the tests that would have caught the blank Records page: they
 * navigate to each route in an insecure context and assert that something the
 * page itself rendered is on screen, with the console-error guard from
 * `fixtures.ts` failing the test if anything threw on the way.
 */
import { test, expect } from "../fixtures";

test.describe("the application shell", () => {
  test("opens on the dashboard", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  });

  test("the sider offers every place the app has", async ({ page }) => {
    await page.goto("/");
    const menu = page.getByRole("menu");

    for (const label of ["Dashboard", "Records", "Statistics", "Pipeline"]) {
      await expect(menu.getByRole("menuitem", { name: label })).toBeVisible();
    }
  });

  test("each sider entry navigates to its page", async ({ page }) => {
    await page.goto("/");

    for (const [label, path, heading] of [
      ["Records", "/records", "Records"],
      ["Statistics", "/statistics", "Statistics"],
      ["Pipeline", "/pipeline", "Pipeline"],
      ["Dashboard", "/", "Dashboard"],
    ] as const) {
      await page.getByRole("menuitem", { name: label }).click();
      await expect(page).toHaveURL(new RegExp(`${path.replace("/", "\\/")}$`));
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    }
  });

  test("the current place is the one marked in the sider", async ({ page }) => {
    await page.goto("/statistics");
    await expect(page.getByRole("menuitem", { name: "Statistics" })).toHaveClass(/selected/);
  });

  test("a record's page still counts as Records in the sider", async ({ page }) => {
    await page.goto("/records/qa-0000");
    await expect(page.getByRole("menuitem", { name: "Records" })).toHaveClass(/selected/);
  });

  test("the menu collapses and the choice survives a reload", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Collapse the menu" }).click();
    await expect(page.getByRole("button", { name: "Expand the menu" })).toBeVisible();

    await page.reload();
    await expect(page.getByRole("button", { name: "Expand the menu" })).toBeVisible();

    // Put it back, so the next test starts where the app ships.
    await page.getByRole("button", { name: "Expand the menu" }).click();
  });

  test("dark mode is offered and applies", async ({ page }) => {
    await page.goto("/");
    const body = page.locator("body");
    const before = await body.evaluate((node) => getComputedStyle(node).backgroundColor);

    await page.getByRole("button", { name: "Toggle dark mode" }).click();
    await expect
      .poll(() => body.evaluate((node) => getComputedStyle(node).backgroundColor))
      .not.toBe(before);

    await page.getByRole("button", { name: "Toggle dark mode" }).click();
  });

  test("the header says how many records there are", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".app-header-count")).toContainText(/records/);
  });

  test("the database banner is absent while the database answers", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("The records database is not answering")).toHaveCount(0);
  });

  test("an unknown route lands on the dashboard rather than nothing", async ({ page }) => {
    await page.goto("/no-such-page");
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  });

  test("the retired saved-searches route lands where the searches now are", async ({ page }) => {
    await page.goto("/searches");
    await expect(page).toHaveURL(/\/records$/);
  });

  test("every page renders without a single console error", async ({ page }) => {
    // The guard in fixtures.ts does the asserting; this walks the routes.
    for (const path of ["/", "/records", "/statistics", "/pipeline", "/records/qa-0000"]) {
      await page.goto(path);
      await expect(page.locator(".page-title")).toBeVisible();
    }
  });
});

test.describe("deep links", () => {
  /**
   * Every route has to work when it is *pasted*, not only when it is navigated
   * to. The two are different code paths: navigating is React Router, pasting
   * is nginx deciding whether the path is the API or the app.
   */
  for (const [path, heading] of [
    ["/", "Dashboard"],
    ["/records", "Records"],
    ["/statistics", "Statistics"],
    ["/pipeline", "Pipeline"],
  ] as const) {
    test(`${path} survives a reload`, async ({ page }) => {
      await page.goto(path);
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();

      await page.reload();
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    });
  }

  test("the API is still reachable on the same origin", async ({ request }) => {
    for (const path of ["/client/meta", "/pipeline/health", "/workers/list", "/swagger.json"]) {
      const answer = await request.get(path);
      expect(answer.status(), path).toBe(200);
      expect(answer.headers()["content-type"], path).toContain("json");
    }
  });
});
