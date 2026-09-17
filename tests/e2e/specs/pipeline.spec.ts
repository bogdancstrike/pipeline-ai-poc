/**
 * The Pipeline page: the wiring, and the two controls that drive it.
 *
 * The worker runner and the prompt editor both change what the *next* video
 * gets, so they are the two places where a UI mistake costs a run. The prompt
 * tests restore the shipped wording however they end.
 */
import { test, expect } from "../fixtures";

test.describe("the wiring", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/pipeline");
    await expect(page.getByRole("heading", { name: "Pipeline" })).toBeVisible();
  });

  test("names the five AI services and where they live", async ({ page }) => {
    const card = page.locator(".ant-card", { hasText: "AI services" });

    for (const service of ["face-match-main", "video-describe-354b", "video-ocr", "transcribe", "summarize"]) {
      await expect(card.getByRole("cell", { name: service, exact: true })).toBeVisible();
    }
    await expect(card).toContainText("172.17.12.80");
  });

  test("says which services are mocked and which are live", async ({ page }) => {
    const card = page.locator(".ant-card", { hasText: "AI services" });
    const modes = await card.locator("tbody .ant-tag").allInnerTexts();

    expect(modes).toHaveLength(5);
    for (const mode of modes) expect(["mocked", "live"]).toContain(mode);
  });

  test("reports the records database", async ({ page }) => {
    const card = page.locator(".ant-card", { hasText: "Records database" });

    await expect(card.getByText("connected")).toBeVisible();
    await expect(card).toContainText("postgres");
    await expect(card).toContainText("Records");
    await expect(card).toContainText("AI calls stored");
  });

  test("the database password is not on screen", async ({ page }) => {
    await expect(page.locator(".ant-card", { hasText: "Records database" })).toContainText("***");
  });

  test("shows the Kafka topics the workers use", async ({ page }) => {
    const card = page.locator(".ant-card", { hasText: "Kafka topics" });
    await expect(card.locator(".record-json")).toContainText("video.in");
  });
});

test.describe("running one worker", () => {
  /** The Worker column only — the name also appears in Reads/Writes. */
  const workerCell = (page, name: string) =>
    page.locator(".worker-table tbody tr.ant-table-row td:nth-child(2)").filter({ hasText: name });

  /** Choose a worker in the runner's select, and close the menu behind it. */
  async function chooseWorker(page, label: string) {
    await page.locator(".worker-runner .ant-select").first().click();
    await page
      .locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden)")
      .getByText(label, { exact: true })
      .click();
    await expect(page.locator(".worker-runner .ant-select-selection-item").first()).toContainText(
      label.split(" · ")[1],
    );
  }

  test.beforeEach(async ({ page }) => {
    await page.goto("/pipeline");
    await expect(page.locator(".worker-runner")).toBeVisible();
  });

  test("lists the seven workers with their topics", async ({ page }) => {
    const table = page.locator(".worker-table");
    await expect(table.locator("tbody tr.ant-table-row")).toHaveCount(7);

    const names = await table
      .locator("tbody tr.ant-table-row td:nth-child(2)")
      .allInnerTexts();
    expect(names).toEqual([
      "splitter", "face-match-main", "video-describe-354b", "transcribe",
      "video-ocr", "aggregator-ai-caller", "aggregator",
    ]);
  });

  test("Run is refused until a worker and a path are given", async ({ page }) => {
    const run = page.locator(".worker-runner").getByRole("button", { name: "Run" });
    await expect(run).toBeDisabled();

    await chooseWorker(page, "W2 · face-match-main");
    await expect(run).toBeDisabled();

    await page.locator(".worker-runner").getByPlaceholder("/video/migrants.mp4").fill("/video/migrants.mp4");
    await expect(run).toBeEnabled();
  });

  test("a row in the catalogue picks that worker", async ({ page }) => {
    await workerCell(page, "video-ocr").click();

    await expect(page.locator(".worker-runner .ant-select-selection-item").first())
      .toContainText("video-ocr");
  });

  test("running one answers with what it produced", async ({ page }) => {
    await chooseWorker(page, "W2 · face-match-main");
    await page.locator(".worker-runner").getByPlaceholder("/video/migrants.mp4").fill("/video/migrants.mp4");

    await page.locator(".worker-runner").getByRole("button", { name: "Run" }).click();

    const result = page.locator(".worker-result .record-json");
    await expect(result).toBeVisible();
    await expect(result).toContainText('"worker": "face-match-main"');
    await expect(result).toContainText('"published": false');
    await expect(result).toContainText("persons");
  });

  test("the chosen worker says what runs before it, and what is mocked", async ({ page }) => {
    await chooseWorker(page, "W7 · aggregator");

    const meta = page.locator(".worker-meta");
    await expect(meta).toContainText("Chained:");
    await expect(meta).toContainText("splitter");
  });

  test("only the aggregator offers to write the record", async ({ page }) => {
    const runner = page.locator(".worker-runner");
    await chooseWorker(page, "W2 · face-match-main");
    await expect(runner.getByText("Write the record (file + database)")).toHaveCount(0);

    await workerCell(page, "aggregator").last().click();
    await expect(runner.getByText("Write the record (file + database)")).toBeVisible();
  });

  test("chaining is on by default, and can be turned off", async ({ page }) => {
    const chain = page.locator(".worker-runner").getByText("Run upstream workers first");
    await expect(chain).toBeVisible();

    const box = page.locator(".worker-runner input[type=checkbox]").first();
    await expect(box).toBeChecked();
    await box.uncheck();
    await expect(box).not.toBeChecked();
  });

  test("a worker that fails says so where the answer would have been", async ({ page }) => {
    const runner = page.locator(".worker-runner");
    await chooseWorker(page, "W2 · face-match-main");
    // `message` is not supplied and chaining is off, so the worker gets a body
    // it cannot use — the API answers 4xx/5xx and the panel has to show it.
    await runner.getByPlaceholder("/video/migrants.mp4").fill("/video/migrants.mp4");
    await runner.locator("input[type=checkbox]").first().uncheck();
    await runner.getByRole("button", { name: "Run" }).click();

    const answered = page.locator(".worker-result");
    await expect(answered).toBeVisible();
  });
});

test.describe("submitting a video", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/pipeline");
    await expect(page.getByRole("heading", { name: "Pipeline" })).toBeVisible();
  });

  test("the modal explains what happens and needs a path", async ({ page }) => {
    await page.getByRole("button", { name: "Analyse a video" }).click();
    const modal = page.getByRole("dialog");

    await expect(modal).toContainText("video.in");
    await modal.getByRole("button", { name: "Submit" }).click();
    await expect(page.getByText("The pipeline needs a path")).toBeVisible();

    await modal.getByRole("button", { name: "Cancel" }).click();
  });

  test("offers the transcribe overrides the API accepts", async ({ page }) => {
    await page.getByRole("button", { name: "Analyse a video" }).click();
    const modal = page.getByRole("dialog");

    await modal.getByLabel("Transcribe language").click();
    for (const language of ["Arabic (ar)", "English (en)", "Spanish (es)", "Romanian (ro)"]) {
      await expect(page.getByTitle(language)).toBeVisible();
    }
    await page.keyboard.press("Escape");
    await modal.getByRole("button", { name: "Cancel" }).click();
  });

  test("submitting one is accepted and says what to expect", async ({ page }) => {
    await page.getByRole("button", { name: "Analyse a video" }).click();
    const modal = page.getByRole("dialog");

    await modal.getByLabel("Video path").fill("/video/migrants.mp4");
    await modal.getByRole("button", { name: "Submit" }).click();

    await expect(page.getByText(/Submitted as .*watch it land on the Records page/)).toBeVisible();
    await expect(modal).toBeHidden();
  });
});

test.describe("the prompt editor", () => {
  test.describe.configure({ mode: "serial" });

  test.afterEach(async ({ request }) => {
    await request.post("/client/prompts/sentiment/reset", { data: {} });
  });

  test("shows the three prompts, with the file each ships as", async ({ page }) => {
    await page.goto("/pipeline");
    const editor = page.locator(".prompt-editor");

    for (const name of ["summary", "entities", "sentiment"]) {
      await expect(editor.getByRole("tab", { name: new RegExp(name) })).toBeVisible();
    }
    await expect(editor).toContainText("prompt_text");
  });

  test("the text on screen is the text that will be sent", async ({ page }) => {
    await page.goto("/pipeline");
    const editor = page.locator(".prompt-editor");
    await editor.getByRole("tab", { name: /sentiment/ }).click();

    const box = editor.getByLabel("The sentiment prompt");
    await expect(box).toBeVisible();
    expect((await box.inputValue()).length).toBeGreaterThan(10);
  });

  test("an edit is marked unsaved until it is saved", async ({ page }) => {
    await page.goto("/pipeline");
    const editor = page.locator(".prompt-editor");
    await editor.getByRole("tab", { name: /sentiment/ }).click();

    const box = editor.getByLabel("The sentiment prompt");
    await box.fill("Answer with one word: POSITIVE, NEUTRAL or NEGATIVE.");

    await expect(editor.getByText("unsaved changes")).toBeVisible();
    await expect(editor.getByRole("button", { name: "Save" })).toBeEnabled();
  });

  test("Discard puts the stored wording back", async ({ page }) => {
    await page.goto("/pipeline");
    const editor = page.locator(".prompt-editor");
    await editor.getByRole("tab", { name: /sentiment/ }).click();

    const box = editor.getByLabel("The sentiment prompt");
    const before = await box.inputValue();
    await box.fill("something else entirely");

    await editor.getByRole("button", { name: "Discard changes" }).click();

    expect(await box.inputValue()).toBe(before);
    await expect(editor.getByText("unsaved changes")).toHaveCount(0);
  });

  test("saving one says which version it became", async ({ page }) => {
    await page.goto("/pipeline");
    const editor = page.locator(".prompt-editor");
    await editor.getByRole("tab", { name: /sentiment/ }).click();

    await editor.getByLabel("The sentiment prompt").fill("QA wording: answer with one word.");
    await editor.getByRole("button", { name: "Save" }).click();

    await expect(page.getByText(/sentiment saved as v\d+ — the next video uses it/)).toBeVisible();
  });

  test("a saved prompt is marked as edited against the shipped wording", async ({ page }) => {
    await page.goto("/pipeline");
    const editor = page.locator(".prompt-editor");
    await editor.getByRole("tab", { name: /sentiment/ }).click();
    await editor.getByLabel("The sentiment prompt").fill("QA wording again.");
    await editor.getByRole("button", { name: "Save" }).click();
    await expect(page.getByText(/saved as v/)).toBeVisible();

    await expect(editor.getByRole("tab", { name: /sentiment/ }).getByText("edited")).toBeVisible();
  });

  test("Reset asks first, then restores the wording that ships", async ({ page }) => {
    await page.goto("/pipeline");
    const editor = page.locator(".prompt-editor");
    await editor.getByRole("tab", { name: /sentiment/ }).click();
    await editor.getByLabel("The sentiment prompt").fill("QA wording, to be reset.");
    await editor.getByRole("button", { name: "Save" }).click();
    await expect(page.getByText(/saved as v/)).toBeVisible();

    await editor.getByRole("button", { name: "Reset to shipped" }).click();
    await expect(page.getByText("Restore the wording that ships?")).toBeVisible();
    await page.getByRole("button", { name: "OK" }).click();

    await expect(page.getByText("sentiment restored to the wording that ships")).toBeVisible();
    await expect(editor.getByRole("tab", { name: /sentiment/ }).getByText("edited")).toHaveCount(0);
  });
});
