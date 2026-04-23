import { test, expect } from "@playwright/test";

const BASE = process.env.UBA_FRONTEND || "http://localhost:3000";

test("Route /observability accessible", async ({ page }) => {
  const resp = await page.goto(BASE + "/observability");
  expect(resp?.status()).toBeLessThan(500);
});
