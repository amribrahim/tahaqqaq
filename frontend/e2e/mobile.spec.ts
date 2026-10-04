import { test, expect, devices, type Page } from "@playwright/test";

// Phone-size checks: the core flow works with touch on small screens and no page scrolls sideways.
const phoneOf = (d: (typeof devices)[string]) => ({ viewport: d.viewport, deviceScaleFactor: d.deviceScaleFactor, isMobile: d.isMobile, hasTouch: d.hasTouch, userAgent: d.userAgent });
const PHONES = [
  { name: "Pixel 7", use: phoneOf(devices["Pixel 7"]) },
  { name: "iPhone 13 (Chrome engine)", use: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true,
    userAgent: devices["iPhone 13"].userAgent } },
];

async function noSideScroll(page: Page) {
  const [sw, iw] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  expect(sw, "page must not scroll horizontally").toBeLessThanOrEqual(iw + 1);
}

for (const phone of PHONES) {
  test.describe(phone.name, () => {
    test.use(phone.use);
    for (const lang of ["ar", "en"] as const) {
      test(`[${lang}] verify flow and every screen fit the phone`, async ({ page }) => {
        await page.addInitScript((l) => { localStorage.setItem("tahqaq.lang", l); localStorage.setItem("tahqaq.banner.dismissed", "1"); localStorage.setItem("tahqaq.explain", "0"); }, lang);
        await page.goto("/");
        await noSideScroll(page);
        await page.getByTestId("input-text").fill(lang === "ar" ? "إنما الأعمال بالنيات" : "The reward of deeds depends upon the intentions");
        await page.getByTestId("verify-btn").tap();
        await expect(page.getByTestId("status-banner")).toBeVisible({ timeout: 30_000 });
        await expect(page.getByTestId("pdf-btn")).toBeVisible();
        await noSideScroll(page);
        for (const p of ["/sources/", "/recent/"]) {
          await page.goto(p);
          await expect(page.locator("main")).toBeVisible();
          await noSideScroll(page);
        }
      });
    }
  });
}
