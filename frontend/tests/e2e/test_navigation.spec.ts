import { test, expect } from "@playwright/test";

// Lance-le avec `npx playwright test`. Sans login complet, on teste
// simplement que les pages s'affichent avec les routes publiques
// (redirection vers /login). Les tests authentifies necessitent un
// token admin injecte via `localStorage`.

const BASE = process.env.UBA_FRONTEND || "http://localhost:3000";

test.describe("UBA dashboard navigation", () => {
  test("Home redirige vers /login si non authentifie", async ({ page }) => {
    await page.goto(BASE + "/");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("Page /login affiche le formulaire", async ({ page }) => {
    await page.goto(BASE + "/login");
    await expect(page.locator("input[type=email], input[name=email]").first()).toBeVisible();
  });

  test("Page /ceo redirige vers /login si non authentifie", async ({ page }) => {
    await page.goto(BASE + "/ceo");
    await expect(page).toHaveURL(/\/login$/);
  });
});
