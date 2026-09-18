/**
 * The Pipeline page: the prompts, the worker runner, and where the services are.
 *
 * The page is three sections in the order somebody reaches for them, with no
 * cards: it used to be five stacked panels — two of them raw JSON and a
 * database status nobody came here for — and the two things it is actually for
 * were buried in the middle. These tests hold that shape, because "cleaned up"
 * is a state a page drifts out of.
 *
 * The worker runner and the prompt editor both change what the *next* video
 * gets, so they are the two places where a UI mistake costs a run. The prompt
 * tests restore the shipped wording however they end.
 */
import { test, expect } from "../fixtures";

test.describe("the shape of the page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/pipeline");
    await expect(page.getByRole("heading", { name: "Pipeline" })).toBeVisible();
  });

  test("is three sections, in the order they are used", async ({ page }) => {
    const headings = await page.locator(".pipeline-section-title").allInnerTexts();
    expect(headings).toEqual(["Summary prompts", "Run one worker", "AI services"]);
  });

  test("draws no cards at all", async ({ page }) => {
    // A heading and a rule say what a card's border said, without the box.
    await expect(page.locator(".ant-card")).toHaveCount(0);
  });

  test("no longer carries the records database or the Kafka topics", async ({ page }) => {
    await expect(page.getByText("Records database")).toHaveCount(0);
    await expect(page.getByText("Kafka topics")).toHaveCount(0);
    await expect(page.getByText("AI calls stored")).toHaveCount(0);
  });

  test("has one primary verb, in the header", async ({ page }) => {
    const primary = page.locator(".page-header button.ant-btn-primary");
    await expect(primary).toHaveCount(1);
    await expect(primary).toHaveText(/Analyse a video/);
  });

  test("fills the width it is given", async ({ page }) => {
    // It was capped at 1060px on the reasoning that prose wants a measure.
    // The page is a workbench: a column of white space beside a control is not
    // restraint, and a cap is easy to reintroduce by accident.
    const section = await page.locator(".pipeline-section").first().boundingBox();
    const content = await page.locator(".app-content").boundingBox();

    expect(section!.width).toBeGreaterThan(content!.width - 64);
  });

  test("each section says what it is for", async ({ page }) => {
    const notes = await page.locator(".pipeline-section-note").allInnerTexts();
    expect(notes.join(" ")).toContain(":8825");
    expect(notes.join(" ")).toContain("Nothing is published to Kafka");
  });
});

test.describe("the services", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/pipeline");
    await expect(page.locator(".service-strip")).toBeVisible();
  });

  test("names the five, one line each", async ({ page }) => {
    const names = await page.locator(".service-name").allInnerTexts();
    expect(names).toEqual([
      "face-match-main",
      "video-describe-354b",
      "video-ocr",
      "transcribe",
      "summarize",
    ]);
  });

  test("gives each one its address", async ({ page }) => {
    const urls = await page.locator(".service-url").allInnerTexts();
    expect(urls).toHaveLength(5);
    for (const url of urls) expect(url).toMatch(/:\d{4}/);
    // The scheme is dropped: five identical `http://` prefixes are noise.
    expect(urls.join(" ")).not.toContain("http://");
  });

  test("says which are mocked and which are live", async ({ page }) => {
    const modes = await page.locator(".service-mode").allInnerTexts();

    expect(modes).toHaveLength(5);
    for (const mode of modes) expect(["mocked", "live"]).toContain(mode.trim());
  });

  test("the full URL is available without leaving the page", async ({ page }) => {
    await page.locator(".service-url").first().hover();
    await expect(page.getByRole("tooltip")).toContainText("http");
  });
});

test.describe("running one worker", () => {
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

  test("the picker offers all seven workers, in pipeline order", async ({ page }) => {
    await page.locator(".worker-runner .ant-select").first().click();
    const options = await page
      .locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item")
      .allInnerTexts();

    expect(options).toEqual([
      "W1 · splitter",
      "W2 · face-match-main",
      "W3 · video-describe-354b",
      "W4 · transcribe",
      "W5 · video-ocr",
      "W6 · aggregator-ai-caller",
      "W7 · aggregator",
    ]);
  });

  test("the six-column catalogue under it is gone", async ({ page }) => {
    // Its Reads and Writes columns were the Kafka topology this page was asked
    // to stop being about; the rest of what it said is on the picker.
    await expect(page.locator(".worker-table")).toHaveCount(0);
    await expect(page.locator(".worker-runner table")).toHaveCount(0);
  });

  test("Run is refused until a worker and a path are given", async ({ page }) => {
    const run = page.locator(".worker-runner").getByRole("button", { name: "Run" });
    await expect(run).toBeDisabled();

    await chooseWorker(page, "W2 · face-match-main");
    await expect(run).toBeDisabled();

    await page.locator(".worker-runner").getByPlaceholder("/video/migrants.mp4").fill("/video/migrants.mp4");
    await expect(run).toBeEnabled();
  });

  test("the path can be run from the keyboard", async ({ page }) => {
    await chooseWorker(page, "W2 · face-match-main");
    await page.locator(".worker-runner").getByPlaceholder("/video/migrants.mp4")
      .fill("/video/migrants.mp4");
    await page.locator(".worker-runner").getByPlaceholder("/video/migrants.mp4").press("Enter");

    await expect(page.locator(".worker-result .record-json")).toBeVisible();
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

  test("the chosen worker says what runs before it", async ({ page }) => {
    await chooseWorker(page, "W7 · aggregator");

    const meta = page.locator(".worker-meta");
    await expect(meta).toContainText("splitter → face-match-main");
    await expect(meta).toContainText("→ aggregator");
  });

  test("a worker that calls a service says whether that call is mocked", async ({ page }) => {
    // W7 makes no AI calls of its own, so it carries no tags — W2 does.
    await chooseWorker(page, "W2 · face-match-main");

    const tags = page.locator(".worker-meta .ant-tag");
    await expect(tags.first()).toContainText(/face-match-main: (mocked|live)/);
  });

  test("only the aggregator offers to write the record", async ({ page }) => {
    const runner = page.locator(".worker-runner");
    await chooseWorker(page, "W2 · face-match-main");
    await expect(runner.getByText("Write the record (file + database)")).toHaveCount(0);

    await chooseWorker(page, "W7 · aggregator");
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
    // The file each prompt ships as, on the line under the box.
    await expect(editor.locator(".ant-tabs-tabpane-active .prompt-meta")).toContainText("summary.txt");
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

    await expect(editor.locator(".ant-tabs-tabpane-active .prompt-meta")).toContainText("unsaved changes");
    await expect(editor.getByRole("button", { name: "Save" })).toBeEnabled();
  });

  test("Discard puts the stored wording back", async ({ page }) => {
    await page.goto("/pipeline");
    const editor = page.locator(".prompt-editor");
    await editor.getByRole("tab", { name: /sentiment/ }).click();

    const box = editor.getByLabel("The sentiment prompt");
    const before = await box.inputValue();
    await box.fill("something else entirely");

    await editor.getByRole("button", { name: "Discard" }).click();

    expect(await box.inputValue()).toBe(before);
    await expect(editor.locator(".ant-tabs-tabpane-active .prompt-meta")).not.toContainText("unsaved changes");
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
