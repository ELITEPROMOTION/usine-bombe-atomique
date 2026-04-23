import { test, expect } from "@playwright/test";

const BASE = process.env.UBA_FRONTEND || "http://localhost:3000";

test("Route /automation repond (meme redirigee)", async ({ page }) => {
  const resp = await page.goto(BASE + "/automation");
  expect([200, 301, 302, 304].includes(resp?.status() ?? 0)).toBeTruthy();
});
