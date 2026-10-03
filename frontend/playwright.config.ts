import { defineConfig } from "@playwright/test";

// Runs against the docker-compose stack (web :3000, api :8000, fixtures :8089).
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "../qa/playwright-report" }]],
  use: {
    baseURL: process.env.BASE_URL || "http://localhost:3000",
    channel: "chrome",
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
  },
});
