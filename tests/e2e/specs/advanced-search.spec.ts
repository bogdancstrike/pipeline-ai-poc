/**
 * The advanced condition builder.
 *
 * The contract it exists to keep: what is being edited is a *draft*. The table
 * behind the drawer keeps showing the last question that was actually run, and
 * closing without pressing Search leaves it exactly as it was. Both halves are
 * tested, because a builder that silently re-ran the page on every keystroke
 * would pass a test that only checked the final result.
 */
import { test, expect, CORPUS, rows, settled, openSeededRecords } from "../fixtures";

/** The drawer, so "Clear" does not also match the search bar's Clear behind it. */
function drawer(page) {
  return page.locator(".ant-drawer-content");
}

/** The option list that is open right now. */
function menu(page) {
  return page.locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden)");
}

async function openBuilder(page) {
  await openSeededRecords(page);
  await page.getByRole("button", { name: "Advanced" }).click();
  await expect(page.getByLabel("Advanced query builder")).toBeVisible();
}

/**
 * Add one rule and give it a field and a value.
 *
 * The waits are not padding: choosing the field makes the library rebuild the
 * operator and the value widget for that field's kind, and clicking the value
 * select before that has happened clicks the one belonging to the old kind.
 */
async function addRule(page, field: string, value: string) {
  // `value` is the label the builder renders, which is prettified from the
  // enum's own spelling: the facet menu says NEGATIVE, this one says Negative.
  await drawer(page).getByRole("button", { name: "Add rule" }).click();
  const builder = page.getByLabel("Advanced query builder");
  await expect(builder.locator(".rule").last()).toBeVisible();

  const rule = builder.locator(".rule").last();
  await rule.locator(".rule--field .ant-select").click();
  await menu(page).getByText(field, { exact: true }).first().click();

  // The value widget only exists once the field has told it what kind it is.
  await expect(rule.locator(".rule--value .ant-select")).toBeVisible();
  await expect(rule.locator(".rule--operator .ant-select-selection-item")).not.toHaveText("");

  await rule.locator(".rule--value .ant-select").click();
  await expect(menu(page).getByText(value, { exact: true }).first()).toBeVisible();
  await menu(page).getByText(value, { exact: true }).first().click();
  await expect(rule.locator(".rule--value .ant-select-selection-item")).toHaveText(value);
}

test.describe("the drawer", () => {
  test("opens with the lesson, which can be closed", async ({ page }) => {
    await openBuilder(page);

    await expect(page.getByText("How this works")).toBeVisible();
    await expect(page.getByText("One comparison: a field, how to compare it")).toBeVisible();

    await page.getByText("How this works").click();
    await expect(page.getByText("One comparison: a field, how to compare it")).toBeHidden();
  });

  test("shows what the condition asks, in words", async ({ page }) => {
    await openBuilder(page);
    await expect(page.locator(".nu-query-inspector pre")).toContainText("All records");
  });

  test("previews the count against the real records", async ({ page }) => {
    await openBuilder(page);
    await expect(page.locator(".nu-advanced-count")).toContainText("records");
  });

  test("offers Clear, Save as… and Search", async ({ page }) => {
    await openBuilder(page);
    const actions = drawer(page).locator(".nu-advanced-actions");

    await expect(actions.getByRole("button", { name: /Clear/ })).toBeVisible();
    await expect(actions.getByRole("button", { name: /Save as/ })).toBeVisible();
    await expect(actions.getByRole("button", { name: /Search/ })).toBeVisible();
  });

  test("Clear is offered but does nothing until there is a rule to clear", async ({ page }) => {
    await openBuilder(page);
    await expect(
      drawer(page).locator(".nu-advanced-actions").getByRole("button", { name: /Clear/ }),
    ).toBeDisabled();
  });
});

test.describe("building a condition", () => {
  test("a rule can be added, given a field and a value, and run", async ({ page }) => {
    await openBuilder(page);
    await addRule(page, "Sentiment", "Negative");

    await expect(page.getByLabel("Advanced query builder").locator(".rule")).toHaveCount(1);
    await expect(page.locator(".nu-query-inspector pre")).toContainText("Sentiment");
    await expect(page.locator(".nu-advanced-count")).toContainText(
      String(CORPUS.sentiments.NEGATIVE),
    );

    await drawer(page).getByRole("button", { name: /Search/ }).click();
    await settled(page);

    await expect(page.locator(".search-count")).toContainText(
      `${CORPUS.sentiments.NEGATIVE} records`,
    );
  });

  test("the condition is shown above the results once it has run", async ({ page }) => {
    await openBuilder(page);
    await addRule(page, "Sentiment", "Negative");
    await drawer(page).getByRole("button", { name: /Search/ }).click();
    await settled(page);

    const strip = page.locator(".condition-strip");
    await expect(strip).toContainText("Advanced:");
    await expect(strip).toContainText("Sentiment");
    await expect(strip).toContainText("1 rule");
  });

  test("the condition can be dropped from the strip", async ({ page }) => {
    await openBuilder(page);
    await addRule(page, "Sentiment", "Negative");
    await drawer(page).getByRole("button", { name: /Search/ }).click();
    await settled(page);
    await expect(page.locator(".condition-strip")).toBeVisible();

    await page.locator(".condition-strip .ant-tag-close-icon").click();
    await settled(page);

    await expect(page.locator(".condition-strip")).toHaveCount(0);
    await expect(page.locator(".search-count")).toContainText(`${CORPUS.size} records`);
  });

  test("closing without pressing Search leaves the table exactly as it was", async ({ page }) => {
    await openSeededRecords(page);
    const before = await rows(page).count();

    await page.getByRole("button", { name: "Advanced" }).click();
    await expect(page.getByLabel("Advanced query builder")).toBeVisible();
    await addRule(page, "Sentiment", "Negative");

    await page.locator(".ant-drawer-close").click();
    await settled(page);

    await expect(rows(page)).toHaveCount(before);
    await expect(page.locator(".condition-strip")).toHaveCount(0);
  });

  test("a half-built rule does not blank the preview", async ({ page }) => {
    await openBuilder(page);
    await drawer(page).getByRole("button", { name: "Add rule" }).click();

    // Field chosen, value not: the count has to stay the whole corpus.
    const builder = page.getByLabel("Advanced query builder");
    await builder.locator(".rule--field .ant-select").first().click();
    await menu(page).getByText("Sentiment", { exact: true }).first().click();

    await expect(page.locator(".nu-advanced-count")).toContainText(`${CORPUS.size}`);
  });

  test("Clear empties the tree and leaves the page behind it alone", async ({ page }) => {
    await openBuilder(page);
    await addRule(page, "Sentiment", "Negative");

    await drawer(page).locator(".nu-advanced-actions").getByRole("button", { name: /Clear/ }).click();
    await expect(page.locator(".nu-query-inspector pre")).toContainText("All records");
  });

  test("a group can be added, so A and (B or C) is sayable", async ({ page }) => {
    await openBuilder(page);
    await drawer(page).getByRole("button", { name: "Add group" }).click();

    const builder = page.getByLabel("Advanced query builder");
    await expect(builder.locator(".group-container")).toHaveCount(2);
    await expect(builder.locator(".group--conjunctions").first()).toBeVisible();
  });

  test("the badge on Advanced counts the rules that ran", async ({ page }) => {
    await openBuilder(page);
    await addRule(page, "Sentiment", "Negative");
    await drawer(page).getByRole("button", { name: /Search/ }).click();
    await settled(page);

    await expect(page.locator(".ant-badge-count")).toContainText("1");
  });
});
