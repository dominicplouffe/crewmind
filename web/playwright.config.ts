import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.NIGHTSQUAD_E2E_PORT ?? 8455);

export default defineConfig({
  testDir: "e2e",
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 20_000 },
  reporter: [["list"]],
  use: {
    // Animations finish at once, so accessibility scans never see an element mid fade-in.
    reducedMotion: "reduce",
    ...devices["Desktop Chrome"],
    baseURL: `http://127.0.0.1:${port}`,
    serviceWorkers: "block",
    trace: "retain-on-failure",
  },
});
