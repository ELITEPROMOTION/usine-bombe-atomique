import { test, expect } from "@playwright/test";

const BASE = process.env.UBA_FRONTEND || "http://localhost:3000";

test("Route /fleet sert HTML", async ({ page }) => {
  const resp = await page.goto(BASE + "/fleet");
  expect(resp?.status()).toBeLessThan(500);
});
