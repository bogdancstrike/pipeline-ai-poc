/**
 * The Export button — the one thing on this screen that leaves the browser.
 *
 * A download is worth testing end to end because everything about it is
 * invisible until it lands: the format, the file name, the BOM, and whether
 * what arrives is the question that was on screen or the page that was showing.
 */
import { test, expect, CORPUS, settled, openSeededRecords } from "../fixtures";

async function download(page, format: "CSV" | "JSON" | "XLSX") {
  await page.getByRole("button", { name: "Export" }).click();
  const started = page.waitForEvent("download");
  await page.getByRole("menuitem", { name: `Export as ${format}` }).click();
  return started;
}

test.describe("exporting", () => {
  test.beforeEach(async ({ page }) => {
    await openSeededRecords(page);
  });

  test("offers every format the API says it can produce", async ({ page, request }) => {
    const advertised = (await (await request.get("/client/meta")).json()).export_formats;

    await page.getByRole("button", { name: "Export" }).click();
    for (const format of advertised) {
      await expect(
        page.getByRole("menuitem", { name: `Export as ${String(format).toUpperCase()}` }),
      ).toBeVisible();
    }
  });

  test("a CSV arrives, named and dated", async ({ page }) => {
    const file = await download(page, "CSV");

    expect(file.suggestedFilename()).toMatch(/^video-records-\d{4}-\d{2}-\d{2}-\d{4}\.csv$/);
  });

  test("the CSV holds the question that was on screen", async ({ page }) => {
    await page.getByLabel("Search every text field").fill(CORPUS.uniquePhrase);
    await settled(page);
    await expect(page.locator(".search-count")).toContainText("1 record");

    const file = await download(page, "CSV");
    const stream = await file.createReadStream();
    const text = await new Promise<string>((resolve) => {
      let out = "";
      stream.on("data", (chunk) => (out += chunk));
      stream.on("end", () => resolve(out));
    });

    expect(text.startsWith("﻿")).toBe(true); // the BOM Excel needs
    const lines = text.trim().split("\n");
    expect(lines).toHaveLength(2); // one header, one row — not the whole corpus
    expect(lines[1]).toContain(CORPUS.name(7));
  });

  test("the export is the whole answer, not the page", async ({ page }) => {
    await expect(page.locator("tr.ant-table-row")).toHaveCount(25);

    const file = await download(page, "CSV");
    const stream = await file.createReadStream();
    const text = await new Promise<string>((resolve) => {
      let out = "";
      stream.on("data", (chunk) => (out += chunk));
      stream.on("end", () => resolve(out));
    });

    expect(text.trim().split("\n")).toHaveLength(CORPUS.size + 1);
  });

  test("a JSON export arrives and parses", async ({ page }) => {
    await page.getByLabel("Search every text field").fill(CORPUS.uniquePhrase);
    await settled(page);

    const file = await download(page, "JSON");
    expect(file.suggestedFilename()).toMatch(/\.json$/);

    const stream = await file.createReadStream();
    const text = await new Promise<string>((resolve) => {
      let out = "";
      stream.on("data", (chunk) => (out += chunk));
      stream.on("end", () => resolve(out));
    });

    const parsed = JSON.parse(text);
    expect(parsed).toHaveLength(1);
    expect(parsed[0].name).toBe(CORPUS.name(7));
  });

  test("an XLSX export arrives as a workbook", async ({ page }) => {
    const file = await download(page, "XLSX");
    expect(file.suggestedFilename()).toMatch(/\.xlsx$/);

    const stream = await file.createReadStream();
    const head = await new Promise<Buffer>((resolve) => {
      const chunks: Buffer[] = [];
      stream.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
      stream.on("end", () => resolve(Buffer.concat(chunks)));
    });

    expect(head.subarray(0, 2).toString()).toBe("PK"); // an OPC package
  });

  test("the reader is told the export happened", async ({ page }) => {
    await download(page, "CSV");
    await expect(page.getByText("Exported as CSV")).toBeVisible();
  });
});
