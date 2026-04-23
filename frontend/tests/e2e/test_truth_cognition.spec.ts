import { test, expect } from "@playwright/test";

const BASE = process.env.UBA_FRONTEND || "http://localhost:3000";

test("Route /cognition sert HTML", async ({ page }) => {
  const resp = await page.goto(BASE + "/cognition");
  expect(resp?.status()).toBeLessThan(500);
});

test("Route /truth sert HTML", async ({ page }) => {
  const resp = await page.goto(BASE + "/truth");
  expect(resp?.status()).toBeLessThan(500);
});
