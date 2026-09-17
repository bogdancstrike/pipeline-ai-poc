import { defineConfig, devices } from "@playwright/test";

/**
 * The client, driven as a person drives it.
 *
 * Against the **frontend origin** (nginx on PORT_FRONTEND), not the Vite dev
 * server: nginx is what proxies /client, /pipeline and /workers onto the API,
 * so this is the only configuration in which the browser talks to one origin —
 * which is the thing that broke in production and would not break in `vite dev`.
 *
 * Nothing is stubbed. Every assertion below is about real rows, produced by
 * `tests/support/seed.py` through the writer W7 uses.
 */
const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:5697";

export default defineConfig({
  testDir: "./specs",
  // Each spec owns its own narrowing of a shared, read-mostly corpus, so they
  // are safe to interleave; the two that write (saved searches, prompts) clean
  // up after themselves and are serialised inside their own files.
  fullyParallel: true,
  workers: process.env.CI ? 2 : 4,
  retries: process.env.CI ? 1 : 0,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  outputDir: "test-results",

  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
    // The stack is served over plain HTTP on a LAN port, which is an insecure
    // context — the condition under which `crypto.randomUUID` is undefined and
    // the Records page used to render blank. Pinning the browser to a non-
    // localhost hostname is what keeps that regression catchable here.
    ignoreHTTPSErrors: true,
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      // The layout is responsive; the sider collapses and the tables scroll.
      name: "mobile",
      use: { ...devices["Pixel 7"] },
      testMatch: /responsive\.spec\.ts/,
    },
  ],
});
