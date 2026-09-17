/**
 * One record as a destination — the permalink behind the drawer.
 *
 * Everything the drawer shows, plus the relatedness the drawer has no room
 * for. The panels are the reason this page exists: a failed service has to be
 * visible *where its text would have been*, because "the transcript is empty"
 * and "transcription refused" look identical otherwise.
 */
import { test, expect, CORPUS, settled } from "../fixtures";

// Record 0 is one of the *live* runs in the corpus (every fourth); record 1 is
// mocked, which is what the "mocked run" tag is about.
const ANALYSED = CORPUS.id(1);

test.describe("the record page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`/records/${ANALYSED}`);
    await expect(page.locator(".record-view")).toBeVisible();
  });

  test("is titled with the video and shows its path", async ({ page }) => {
    await expect(page.getByRole("heading", { name: CORPUS.name(1) })).toBeVisible();
    await expect(page.locator(".page-blurb")).toContainText("/app/videos/qa/");
  });

  test("states the facts a reader checks first", async ({ page }) => {
    const facts = page.locator(".record-facts");

    await expect(facts).toContainText("Status");
    await expect(facts).toContainText("Analysed");
    await expect(facts).toContainText("Path");
    await expect(facts).toContainText("Processing");
    await expect(facts).toContainText("Model");
    await expect(facts).toContainText("Record id");
  });

  test("marks a mocked run as mocked", async ({ page }) => {
    await expect(page.locator(".record-facts")).toContainText("mocked run");
  });

  test("shows the seven panels in pipeline order", async ({ page }) => {
    const titles = await page.locator(".enrichment .ant-card-head-title").allInnerTexts();

    expect(titles[0]).toBe("Face match");
    expect(titles[1]).toBe("Description");
    expect(titles[2]).toContain("Transcript");
    expect(titles[3]).toContain("On-screen text");
    expect(titles[4]).toBe("Summary");
    expect(titles[5]).toContain("Entities");
    expect(titles[6]).toBe("Sentiment");
  });

  test("names the service behind every panel", async ({ page }) => {
    const notes = await page.locator(".enrichment .card-note").allInnerTexts();

    expect(notes.join(" ")).toContain(":8821");
    expect(notes.join(" ")).toContain(":8822");
    expect(notes.join(" ")).toContain(":8823");
    expect(notes.join(" ")).toContain(":8824");
    expect(notes.filter((note) => note.includes(":8825"))).toHaveLength(3);
  });

  test("the summary and the transcript carry their text", async ({ page }) => {
    const summary = page.locator(".enrichment-card", { hasText: "Summary" }).first();
    await expect(summary).toContainText("Record 1:");

    const transcript = page.locator(".enrichment-card", { hasText: "Transcript" }).first();
    await expect(transcript).toContainText("Speaker one");
  });

  test("the entities are shown as typed tags", async ({ page }) => {
    const entities = page.locator(".enrichment-card", { hasText: "Entities" }).first();
    await expect(entities.locator(".ant-tag").first()).toContainText(/LOCATION|NAME|ORG|DATE/);
  });

  test("the calls tab lists what each service did", async ({ page }) => {
    await page.getByRole("tab", { name: /Calls/ }).click();

    await expect(page.getByRole("cell", { name: "face-match-main" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "transcribe", exact: true })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Tokens in/out" })).toBeVisible();
  });

  test("the JSON tab shows the record as it was written to disk", async ({ page }) => {
    await page.getByRole("tab", { name: "JSON" }).click();
    const json = page.locator(".record-json");

    await expect(json).toContainText("enrichment");
    await expect(json).toContainText("face_match");
    await expect(json).toContainText("analysed_at");
  });

  test("offers the videos that share an entity", async ({ page }) => {
    await expect(page.getByText("Videos sharing an entity")).toBeVisible();
  });

  test("a related video is a link, and it names what is shared", async ({ page }) => {
    const list = page.locator(".ant-card", { hasText: "Videos sharing an entity" });
    const first = list.locator(".ant-list-item").first();

    if (await first.count()) {
      await expect(first.getByRole("link")).toBeVisible();
      await expect(first.locator(".ant-tag").first()).toBeVisible();
    }
  });

  test("goes back to the list", async ({ page }) => {
    await page.getByRole("button", { name: "Back to records" }).click();
    await expect(page).toHaveURL(/\/records$/);
    await settled(page);
  });
});

test.describe("a record whose service failed", () => {
  test("says which one, and where its text would have been", async ({ page }) => {
    await page.goto("/records?q=qa-&status=partial");
    await settled(page);
    await page.locator("tr.ant-table-row").first().locator(".cell-video a").click();

    const drawer = page.getByRole("dialog");
    await expect(drawer.getByText(/service\(s\) did not answer/)).toBeVisible();

    // The error is shown inside the panel of the service that produced it.
    await expect(drawer.locator(".enrichment-card", { hasText: "This service did not answer" }))
      .toHaveCount(1);
  });

  test("the failed record is marked partial in the facts", async ({ page }) => {
    await page.goto("/records?q=qa-&status=partial");
    await settled(page);
    const id = await page.locator("tr.ant-table-row").first().locator(".cell-video a").innerText();

    await page.goto(`/records/${id.replace(".mp4", "")}`);
    await expect(page.locator(".record-facts")).toContainText("partial");
  });
});

test.describe("a record that does not exist", () => {
  // The page's job here is to render a failure, and a 404 fetch is a console
  // error in every browser.
  test.use({ expectedConsoleErrors: [/Failed to load resource.*404/] });

  test("says so rather than showing an empty shell", async ({ page }) => {
    await page.goto("/records/no-such-record");
    await expect(page.getByText("This record could not be read")).toBeVisible();
  });
});
