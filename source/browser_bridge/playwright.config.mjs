import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './test', testMatch: '*.browser.mjs', workers: 1,
  use: { baseURL: 'https://127.0.0.1:18444', ignoreHTTPSErrors: true },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }, { name: 'webkit', use: { browserName: 'webkit' } }],
  webServer: { command: 'node test/browser-fixture.mjs', url: 'https://127.0.0.1:18444/', ignoreHTTPSErrors: true, reuseExistingServer: false },
});
