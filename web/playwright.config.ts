import { defineConfig, devices } from "@playwright/test"

// Web-server port: overridable, but defaults to 3001 so it never collides with a
// developer's own `next dev` on 3000. baseURL and webServer.url MUST stay in sync
// with this value, and the spawned server is told to bind it explicitly.
const PORT = Number(process.env.PLAYWRIGHT_WEB_PORT ?? 3001)
const BASE_URL = `http://localhost:${PORT}`

// CI uses a production build: turbopack dev cold-compile is flaky under the load of
// a full e2e suite. Local runs use the fast dev server and reuse an existing one.
const webServerCommand = process.env.CI
  ? `npm run build && npm run start -- --port ${PORT}`
  : `npm run dev -- --port ${PORT}`

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: 1,
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: webServerCommand,
    url: BASE_URL,
    // CI always starts a fresh server; locally reuse a running one for speed.
    reuseExistingServer: !process.env.CI,
    // Generous: covers a cold production build (CI) or first turbopack compile (local).
    timeout: 120_000,
  },
})
