import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";
import axePkg from "axe-core/package.json";

// Automated accessibility audit (axe-core, WCAG 2.1 A/AA rules) of every screen in both languages.
// The full findings are written to qa/a11y-report.md (local, not published); the test fails on any violation.
const OUT = path.resolve(__dirname, "../../qa/a11y-report.md");
type Lang = "ar" | "en";
const rows: string[] = [];

async function seed(page: Page, lang: Lang) {
  await page.addInitScript((l) => {
    localStorage.setItem("tahqaq.lang", l);
    localStorage.setItem("tahqaq.explain", "0");
  }, lang);
}

const SCREENS: { name: string; path: string; ready: (p: Page) => Promise<void> }[] = [
  { name: "home", path: "/", ready: async (p) => { await expect(p.getByTestId("verify-btn")).toBeVisible(); } },
  { name: "result (verified)", path: `/result/?id=a11y-v&text=${encodeURIComponent("إنما الأعمال بالنيات")}`,
    ready: async (p) => { await expect(p.getByTestId("status-banner")).toBeVisible({ timeout: 30_000 }); } },
  { name: "result (abstain)", path: `/result/?id=a11y-a&text=${encodeURIComponent("الصبر مفتاح كل باب مغلق في الدنيا والآخرة")}`,
    ready: async (p) => { await expect(p.getByTestId("status-banner")).toBeVisible({ timeout: 30_000 }); } },
  { name: "sources", path: "/sources/", ready: async (p) => { await expect(p.locator("main")).toBeVisible(); } },
  { name: "recent", path: "/recent/", ready: async (p) => { await expect(p.locator("main")).toBeVisible(); } },
];

for (const lang of ["ar", "en"] as Lang[]) {
  for (const s of SCREENS) {
    test(`[${lang}] ${s.name} has no WCAG 2.1 AA violations`, async ({ page }) => {
      await seed(page, lang);
      await page.goto(s.path);
      await s.ready(page);
      await page.waitForTimeout(500);
      const res = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      rows.push(`| ${lang} | ${s.name} | ${res.passes.length} | ${res.violations.length} | ${res.violations.map((v) => `${v.id} (${v.nodes.length})`).join(", ") || "—"} |`);
      expect(res.violations.map((v) => `${v.id}: ${v.help} → ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(" | ")}`)).toEqual([]);
    });
  }
}

test.afterAll(() => {
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, [
    "# Accessibility audit — تحقّق", "",
    `axe-core ${axePkg.version}, rules tagged WCAG 2.0/2.1 A and AA, run with Playwright on ${new Date().toISOString().slice(0, 10)}.`, "",
    "| Lang | Screen | Rules passed | Violations | Details |", "|---|---|---|---|---|", ...rows, "",
  ].join("\n"));
});
