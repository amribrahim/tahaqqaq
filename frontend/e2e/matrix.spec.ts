import { test, expect, type Page, type ConsoleMessage } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";

const SHOTS = path.resolve(__dirname, "../../qa/screenshots");
const IMG = path.resolve(__dirname, "../../qa/fixtures/images");
const API = process.env.API_URL || "http://localhost:8000";
fs.mkdirSync(SHOTS, { recursive: true });

type Lang = "ar" | "en";
const LANGS: Lang[] = ["ar", "en"];

const errors: string[] = [];
function watch(page: Page) {
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m: ConsoleMessage) => {
    // network status lines for intentionally invalid requests (415/422/413) are expected
    if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errors.push(`console: ${m.text()}`);
  });
}

async function open(page: Page, lang: Lang, pathname = "/", opts: { banner?: boolean; explain?: boolean } = {}) {
  await page.addInitScript(({ lang, banner, explain }) => {
    // seed once per tab so that in-page toggles (and their persistence) are not overwritten on reload
    if (!sessionStorage.getItem("e2e.seeded")) {
      localStorage.setItem("tahqaq.lang", lang);
      sessionStorage.setItem("e2e.seeded", "1");
    }
    if (!banner) localStorage.setItem("tahqaq.banner.dismissed", "1");
    // the matrix skips the optional LLM explanation to spare free-tier quotas; one test enables it
    localStorage.setItem("tahqaq.explain", explain ? "1" : "0");
  }, { lang, banner: !!opts.banner, explain: !!opts.explain });
  watch(page);
  await page.goto(pathname);
  await expect(page.locator("html")).toHaveAttribute("dir", lang === "ar" ? "rtl" : "ltr");
}

async function verifyText(page: Page, lang: Lang, text: string) {
  await open(page, lang);
  await page.getByTestId("input-text").fill(text);
  await page.getByTestId("verify-btn").click();
  await page.waitForURL(/\/result\//);
  await expect(page.getByTestId("status-banner").or(page.getByTestId("error-card"))).toBeVisible({ timeout: 30_000 });
}

async function shot(page: Page, name: string) {
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true });
}

const state = (page: Page) => page.getByTestId("status-banner").getAttribute("data-state");

test.afterEach(async () => {
  expect(errors, "browser console / page errors").toEqual([]);
  errors.length = 0;
});

// ---------------------------------------------------------------- Arabic interface: Arabic texts
test.describe("[ar] text input", () => {
  const lang: Lang = "ar";
  test("sahih exact", async ({ page }) => {
    await verifyText(page, lang, "إنما الأعمال بالنيات");
    expect(await state(page)).toBe("verified");
    await expect(page.getByTestId("grade-chip").first()).toHaveText("صحيح");
    await expect(page.getByTestId("source-link")).toHaveAttribute("href", /dorar\.net\/hadith|shamela\.ws/);
    await expect(page.getByTestId("grade-card")).toContainText("صحيح البخاري");
    await expect(page.getByTestId("number")).toHaveText("١");
    // the approved reference: rulings fetched from الدرر السنية for the matched hadith (or a clear fallback with the link)
    await expect(page.getByTestId("dorar-card")).toBeVisible();
    await expect(page.getByTestId("dorar-ruling").first().or(page.getByTestId("dorar-unavailable"))).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("dorar-link")).toHaveAttribute("href", /dorar\.net\/hadith/);
    await shot(page, "ar-verified");
  });

  test("sahih with typos, missing and extra words → diff", async ({ page }) => {
    await verifyText(page, lang, "إنما الاعمال بالنيه ولكل امرء ما نوى يا إخوان");
    expect(["verified", "partial"]).toContain(await state(page));
    await expect(page.getByTestId("diff-card")).toBeVisible();
    await expect(page.locator(".tok-del, .tok-ins").first()).toBeVisible();
    await shot(page, "ar-partial");
  });

  test("famous fabricated → موضوع with grader and source", async ({ page }) => {
    await verifyText(page, lang, "حب الوطن من الإيمان");
    expect(await state(page)).toBe("unreliable");
    await expect(page.getByTestId("grade-chip").first()).toHaveText("موضوع");
    await expect(page.getByTestId("grader")).not.toHaveText("—");
    await expect(page.getByTestId("source-link")).toHaveAttribute("href", /dorar\.net/);
    await expect(page.getByTestId("state-label")).toContainText("موضوع");
    await shot(page, "ar-unreliable-mawdu");
  });

  test("weak hadith → ضعيف with grader", async ({ page }) => {
    await verifyText(page, lang, "صوموا تصحوا");
    expect(await state(page)).toBe("unreliable");
    await expect(page.getByTestId("grade-chip").first()).toHaveText("ضعيف");
    await expect(page.getByTestId("grader")).toContainText("الألباني");
    await shot(page, "ar-unreliable-daif");
  });

  test("ayah quoted as hadith → آية with surah/ayah and note", async ({ page }) => {
    await verifyText(page, lang, "قال رسول الله: وقل رب زدني علما");
    await expect(page.getByTestId("quran-note")).toBeVisible();
    await expect(page.getByTestId("grade-card")).toContainText("طه");
    await expect(page.getByTestId("number")).toHaveText("١١٤");
    await expect(page.getByTestId("diff-card")).toContainText(/زِدْنِ[يى] عِلْمًا/);  // Uthmani script uses ى
    await shot(page, "ar-quran");
  });

  test("misquoted ayah → correct text with diff", async ({ page }) => {
    await verifyText(page, lang, "وقل ربي زدني علما");
    await expect(page.getByTestId("diff-card")).toContainText(/زِدْنِ[يى] عِلْمًا/);
    await expect(page.locator(".tok-del, .tok-ins").first()).toBeVisible();
    await shot(page, "ar-quran-misquote");
  });

  test("near-meaning text → uncertain with closest-text note", async ({ page }) => {
    // close in form to «النظافة من الإيمان» (itself a curated fabricated saying) but a different text
    await verifyText(page, lang, "الصدق من الإيمان");
    expect(["uncertain", "partial"]).toContain(await state(page));
    if ((await state(page)) === "uncertain") await expect(page.getByTestId("grade-card")).toContainText("للنص الأقرب");
    await expect(page.getByTestId("candidates")).toBeVisible();
    await shot(page, "ar-uncertain");
  });

  test("invented text → abstain, nearest results, review, no grade", async ({ page }) => {
    await verifyText(page, lang, "من قرأ هذا النص غُفر له كل ذنب");
    expect(["abstain", "uncertain"]).toContain(await state(page));
    if ((await state(page)) === "abstain") {
      await expect(page.getByTestId("abstain-card")).toBeVisible();
      await expect(page.getByTestId("grade-card")).toHaveCount(0);
      await expect(page.getByTestId("review-btn")).toBeVisible();
    }
    await expect(page.getByTestId("candidates")).toBeVisible();
    await shot(page, "ar-abstain");
  });

  test("personal fatwa question → referral, no verdict", async ({ page }) => {
    await verifyText(page, lang, "هل يجوز لي أن أفعل كذا في زواجي؟");
    expect(await state(page)).toBe("referral");
    await expect(page.getByTestId("grade-card")).toHaveCount(0);
    await expect(page.getByTestId("abstain-card")).toBeVisible();
    await shot(page, "ar-referral");
  });

  test("empty, whitespace and >2000 chars are blocked client-side", async ({ page }) => {
    await open(page, lang);
    const btn = page.getByTestId("verify-btn");
    await expect(btn).toBeDisabled();
    await page.getByTestId("input-text").fill("    ");
    await expect(btn).toBeDisabled();
    await page.getByTestId("input-text").fill("ا".repeat(2001));
    await expect(btn).toBeDisabled();
    await expect(page.getByTestId("counter")).toHaveCSS("color", "rgb(168, 50, 74)");
    await page.getByTestId("input-text").fill("نص");
    await expect(btn).toBeEnabled();
  });

  test("an English text is not sent: clear message, one click switches the interface and verifies in English", async ({ page }) => {
    await open(page, lang);
    await expect(page.getByTestId("tab-text")).toContainText("عربي");
    await page.getByTestId("input-text").fill("The reward of deeds depends upon the intentions");
    await page.getByTestId("verify-btn").click();
    await expect(page.getByTestId("lang-error")).toBeVisible();
    await expect(page).not.toHaveURL(/\/result\//);
    await shot(page, "ar-language-mismatch");
    await page.getByTestId("lang-switch").click();
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
    await expect(page.getByTestId("input-text")).toHaveValue("The reward of deeds depends upon the intentions");
    await page.getByTestId("verify-btn").click();
    await expect(page.getByTestId("status-banner")).toBeVisible({ timeout: 30_000 });
    expect(await state(page)).toBe("verified");
  });

  test("emoji, gibberish and mixed text are graceful", async ({ page }) => {
    for (const text of ["😀😀😀 🙏", "سيبسي شسيب ضصثق", "مرحبا بكم hello 😀"]) {
      await verifyText(page, lang, text);
      await expect(page.getByTestId("status-banner")).toBeVisible();
      expect(["abstain", "uncertain"]).toContain(await state(page));
    }
  });
});

// ---------------------------------------------------------------- English interface: English texts
test.describe("[en] text input", () => {
  const lang: Lang = "en";
  test("sahih, published translation → verified with the Arabic source", async ({ page }) => {
    await verifyText(page, lang, "The reward of deeds depends upon the intentions and every person will get the reward according to what he has intended");
    expect(await state(page)).toBe("verified");
    await expect(page.getByTestId("grade-chip").first()).toHaveText("Sahih");
    await expect(page.getByTestId("grade-card")).toContainText("Sahih al-Bukhari");
    await expect(page.getByTestId("number")).toHaveText("1");
    await expect(page.getByTestId("source-link")).toHaveAttribute("href", /dorar\.net\/hadith|shamela\.ws/);
    await expect(page.getByTestId("dorar-card")).toBeVisible();
    await shot(page, "en-verified");
  });

  test("free translation of a sahih hadith → Arabic original + translation card", async ({ page }) => {
    await verifyText(page, lang, "Actions are judged by intentions and every person will get what he intended");
    // a free paraphrase matches on meaning: attributed once a strong model confirms it, otherwise the closest text
    expect(["verified", "partial", "uncertain"]).toContain(await state(page));
    await expect(page.getByTestId("grade-card")).toContainText("Sahih");
    await expect(page.getByTestId("translation-card")).toBeVisible();
    await expect(page.getByTestId("translation-card")).toContainText("الأَعْمَالُ");
    await shot(page, "en-translation");
  });

  test("inaccurate English translation → issues listed", async ({ page }) => {
    await verifyText(page, lang, "None of you is a Muslim until he loves for his brother what he loves for himself.");
    await expect(page.getByTestId("translation-card")).toBeVisible();
    await expect(page.getByTestId("issues").locator("li").first()).toBeVisible();
    await shot(page, "en-translation-issues");
  });

  test("famous fabricated → Fabricated with grader and source", async ({ page }) => {
    await verifyText(page, lang, "Love of the homeland is part of faith");
    expect(await state(page)).toBe("unreliable");
    await expect(page.getByTestId("grade-chip").first()).toHaveText("Fabricated");
    await expect(page.getByTestId("grader")).not.toHaveText("—");
    await expect(page.getByTestId("source-link")).toHaveAttribute("href", /dorar\.net/);
    await expect(page.getByTestId("state-label")).toContainText("Fabricated");
    await shot(page, "en-unreliable-mawdu");
  });

  test("weak hadith → Weak with grader", async ({ page }) => {
    await verifyText(page, lang, "Fast and you will be healthy");
    expect(await state(page)).toBe("unreliable");
    await expect(page.getByTestId("grade-chip").first()).toHaveText("Weak");
    await expect(page.getByTestId("grader")).toContainText("Al-Albani");
    await shot(page, "en-unreliable-daif");
  });

  test("verse quoted as a hadith → Qur'an with surah/ayah and note", async ({ page }) => {
    await verifyText(page, lang, "The Prophet said: My Lord, increase me in knowledge");
    await expect(page.getByTestId("quran-note")).toBeVisible();
    await expect(page.getByTestId("grade-card")).toContainText("Taha");
    await expect(page.getByTestId("number")).toHaveText("114");
    await shot(page, "en-quran");
  });

  test("invented text → abstain, nearest results, review, no grade", async ({ page }) => {
    await verifyText(page, lang, "Whoever reads this text will have all his sins forgiven");
    expect(["abstain", "uncertain"]).toContain(await state(page));
    if ((await state(page)) === "abstain") {
      await expect(page.getByTestId("abstain-card")).toBeVisible();
      await expect(page.getByTestId("grade-card")).toHaveCount(0);
      await expect(page.getByTestId("review-btn")).toBeVisible();
    }
    await shot(page, "en-abstain");
  });

  test("personal fatwa question → referral, no verdict", async ({ page }) => {
    await verifyText(page, lang, "Is it permissible for me to delay zakat until next year?");
    expect(await state(page)).toBe("referral");
    await expect(page.getByTestId("grade-card")).toHaveCount(0);
    await expect(page.getByTestId("abstain-card")).toBeVisible();
    await shot(page, "en-referral");
  });

  test("empty, whitespace and >2000 chars are blocked client-side", async ({ page }) => {
    await open(page, lang);
    const btn = page.getByTestId("verify-btn");
    await expect(btn).toBeDisabled();
    await page.getByTestId("input-text").fill("    ");
    await expect(btn).toBeDisabled();
    await page.getByTestId("input-text").fill("a".repeat(2001));
    await expect(btn).toBeDisabled();
    await expect(page.getByTestId("counter")).toHaveCSS("color", "rgb(168, 50, 74)");
    await page.getByTestId("input-text").fill("text");
    await expect(btn).toBeEnabled();
  });

  test("an Arabic text is not sent: clear message, one click switches the interface", async ({ page }) => {
    await open(page, lang);
    await expect(page.getByTestId("tab-text")).toContainText("English");
    await page.getByTestId("input-text").fill("إنما الأعمال بالنيات");
    await page.getByTestId("verify-btn").click();
    await expect(page.getByTestId("lang-error")).toBeVisible();
    await expect(page).not.toHaveURL(/\/result\//);
    await shot(page, "en-language-mismatch");
    await page.getByTestId("lang-switch").click();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await page.getByTestId("verify-btn").click();
    await expect(page.getByTestId("status-banner")).toBeVisible({ timeout: 30_000 });
    expect(await state(page)).toBe("verified");
  });

  test("another language is refused by the server with a clear message, no translation, no switch offered", async ({ page }) => {
    await verifyText(page, lang, "Les actions ne valent que par les intentions, et chacun n'aura que ce qu'il a eu l'intention de faire");
    await expect(page.getByTestId("error-card")).toHaveAttribute("data-code", "wrong_language");
    await expect(page.getByTestId("error-card")).toContainText("not in English");
    await expect(page.getByTestId("error-lang-switch")).toHaveCount(0);
    await shot(page, "en-other-language");
  });

  test("a direct link with an Arabic text offers the switch, and verifies it in Arabic", async ({ page }) => {
    await open(page, lang, "/result/?id=e2e-switch&text=" + encodeURIComponent("إنما الأعمال بالنيات"));
    await expect(page.getByTestId("error-card")).toHaveAttribute("data-code", "wrong_language", { timeout: 30_000 });
    await page.getByTestId("error-lang-switch").click();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByTestId("status-banner")).toBeVisible({ timeout: 30_000 });
    expect(await state(page)).toBe("verified");
  });

  test("emoji, gibberish and mixed text are graceful", async ({ page }) => {
    for (const text of ["😀😀😀 🙏", "asdkjh qwe zxcv mnb", "hello world مرحبا 123 😀"]) {
      await verifyText(page, lang, text);
      await expect(page.getByTestId("status-banner")).toBeVisible();
      expect(["abstain", "uncertain"]).toContain(await state(page));
    }
  });
});

// ---------------------------------------------------------------- images
test.describe("[ar] image input", () => {
  const lang: Lang = "ar";
  test("arabic hadith image → OCR shown, editable, same verdict", async ({ page }) => {
    await open(page, lang);
    await page.getByTestId("tab-image").click();
    await page.getByTestId("input-file").setInputFiles(path.join(IMG, "ar.png"));
    const ocr = page.getByTestId("ocr-text");
    await expect(ocr).toBeVisible({ timeout: 60_000 });
    // OCR may come from the vision model (diacritics kept) or Tesseract: match the word ignoring diacritics
    await expect(ocr).toHaveValue(/ا[ً-ْ]*ل[ً-ْ]*[أا][ً-ْ]*ع[ً-ْ]*م[ً-ْ]*ا[ً-ْ]*ل/);
    await ocr.fill((await ocr.inputValue()).replace("رواه البخاري", ""));  // user can edit before verifying
    await page.getByTestId("verify-btn").click();
    await expect(page.getByTestId("status-banner")).toBeVisible({ timeout: 30_000 });
    expect(["verified", "partial"]).toContain(await state(page));
    await expect(page.getByTestId("grade-card")).toContainText("صحيح البخاري");
    await expect(page.getByTestId("extracted-card")).toBeVisible();
    await shot(page, "ar-image");
  });

  test("sunnah.com screenshot with chain of narrators → whole text for review, verdict Bukhari 1", async ({ page }) => {
    await open(page, lang);
    await page.getByTestId("tab-image").click();
    await page.getByTestId("input-file").setInputFiles(path.join(IMG, "sunnah-bukhari1.png"));
    const ocr = page.getByTestId("ocr-text");
    await expect(ocr).toBeVisible({ timeout: 60_000 });
    const value = (await ocr.inputValue()).replace(/[ً-ْٰ]/g, "");
    expect(value).toMatch(/سفيان/);          // the chain of narrators is there …
    expect(value).toMatch(/هاجر إل[يى]ه/);  // … and the end of the matn: nothing was cut
    await page.getByTestId("verify-btn").click();
    await expect(page.getByTestId("status-banner")).toBeVisible({ timeout: 30_000 });
    expect(["verified", "partial"]).toContain(await state(page));
    await expect(page.getByTestId("grade-card")).toContainText("صحيح البخاري");
    await shot(page, "ar-image-sunnah");
  });

  test("blurry image → OCR result editable, no crash", async ({ page }) => {
    await open(page, lang);
    await page.getByTestId("tab-image").click();
    await page.getByTestId("input-file").setInputFiles(path.join(IMG, "ar-blurry.png"));
    await expect(page.getByTestId("ocr-text").or(page.getByTestId("ocr-error"))).toBeVisible({ timeout: 60_000 });
    if (await page.getByTestId("ocr-text").isVisible()) {
      await page.getByTestId("ocr-text").fill("إنما الأعمال بالنيات");
      await page.getByTestId("verify-btn").click();
      await expect(page.getByTestId("status-banner")).toBeVisible({ timeout: 30_000 });
    }
  });
});

test.describe("[en] image input", () => {
  const lang: Lang = "en";
  test("english text image → OCR + verdict", async ({ page }) => {
    await open(page, lang);
    await page.getByTestId("tab-image").click();
    await page.getByTestId("input-file").setInputFiles(path.join(IMG, "en.png"));
    const ocr = page.getByTestId("ocr-text");
    await expect(ocr).toBeVisible({ timeout: 60_000 });
    await expect(ocr).toHaveValue(/Muslim/);
    await page.getByTestId("verify-btn").click();
    await expect(page.getByTestId("status-banner")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("translation-card")).toBeVisible();
    await shot(page, "en-image");
  });
});

for (const lang of LANGS) {
  test.describe(`[${lang}] image files`, () => {
    test("non-image, 0-byte and >10MB files are rejected", async ({ page }) => {
      await open(page, lang);
      await page.getByTestId("tab-image").click();
      for (const f of ["notimage.txt", "empty.png", "big.png"]) {
        await page.getByTestId("input-file").setInputFiles(path.join(IMG, f));
        await expect(page.getByTestId("ocr-error")).toBeVisible({ timeout: 30_000 });
        await expect(page.getByTestId("verify-btn")).toBeDisabled();
      }
      await shot(page, `${lang}-image-rejected`);
    });
  });
}

// ---------------------------------------------------------------- links
async function verifyUrl(page: Page, lang: Lang, url: string) {
  await open(page, lang);
  await page.getByTestId("tab-url").click();
  await page.getByTestId("input-url").fill(url);
  await page.getByTestId("verify-btn").click();
  await page.waitForURL(/\/result\//);
  await expect(page.getByTestId("status-banner").or(page.getByTestId("error-card"))).toBeVisible({ timeout: 30_000 });
}

test.describe("[ar] link input", () => {
  test("page containing a hadith → extracted, same verdict", async ({ page }) => {
    await verifyUrl(page, "ar", "http://fixtures/hadith.html");
    expect(["verified", "partial"]).toContain(await state(page));
    await expect(page.getByTestId("grade-card")).toContainText("صحيح البخاري");
    await expect(page.getByTestId("extracted-card")).toBeVisible();
    await shot(page, "ar-link");
  });

  test("page with two hadiths → both segments listed with their own matches", async ({ page }) => {
    await verifyUrl(page, "ar", "http://fixtures/multi.html");
    expect(["verified", "partial"]).toContain(await state(page));
    await expect(page.getByTestId("segments-card")).toBeVisible();
    expect(await page.getByTestId("segment").count()).toBeGreaterThanOrEqual(2);
    await expect(page.getByTestId("segments-card")).toContainText("صحيح مسلم");
    await shot(page, "ar-link-segments");
  });
});

test.describe("[en] link input", () => {
  test("English page containing a hadith → extracted, translation checked", async ({ page }) => {
    await verifyUrl(page, "en", "http://fixtures/images/en.html");
    expect(["verified", "partial", "uncertain"]).toContain(await state(page));
    await expect(page.getByTestId("translation-card")).toBeVisible();
    await expect(page.getByTestId("extracted-card")).toBeVisible();
    await shot(page, "en-link");
  });

  test("Arabic page in the English interface → clear language message", async ({ page }) => {
    await verifyUrl(page, "en", "http://fixtures/hadith.html");
    await expect(page.getByTestId("error-card")).toHaveAttribute("data-code", "wrong_language");
  });
});

for (const lang of LANGS) {
  test(`[${lang}] link errors: no text, unreachable, non-http, redirect loop → graceful errors`, async ({ page }) => {
    for (const url of ["http://fixtures/empty.html", "http://nonexistent.invalid/page", "javascript:alert(1)", "http://fixtures/loop1"]) {
      await verifyUrl(page, lang, url);
      await expect(page.getByTestId("error-card")).toHaveAttribute("data-code", "url_unreachable");
    }
    await shot(page, `${lang}-link-error`);
  });
}

test.describe("cross-cutting", () => {
  test("language toggle switches strings, direction and examples", async ({ page }) => {
    await open(page, "ar");
    await expect(page.getByTestId("verify-btn")).toHaveText(/تحقّق/);
    await page.getByTestId("lang-en").click();
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await expect(page.getByTestId("verify-btn")).toHaveText(/Verify/);
    await expect(page.getByTestId("example-ex2")).toContainText("Fabricated");
    await expect(page.locator("nav").first()).toContainText("Sources & methodology");
    // no horizontal overflow at 1440px
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr");  // persisted
    await page.getByTestId("lang-ar").click();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  });

  for (const lang of LANGS) {
    test(`[${lang}] loading indicator shows 4 steps and result renders within 10s`, async ({ page }) => {
      await page.route("**/api/verify/stream", async (route) => { await new Promise((r) => setTimeout(r, 1200)); await route.continue(); });
      await open(page, lang);
      await page.getByTestId("input-text").fill(lang === "ar" ? "إنما الأعمال بالنيات" : "The reward of deeds depends upon the intentions");
      const t0 = Date.now();
      await page.getByTestId("verify-btn").click();
      await expect(page.getByTestId("loading-panel")).toBeVisible();
      await expect(page.getByTestId("loading-step")).toHaveCount(4);
      await shot(page, `${lang}-loading`);
      await expect(page.getByTestId("status-banner")).toBeVisible({ timeout: 10_000 });
      expect(Date.now() - t0).toBeLessThan(10_000);
    });

    test(`[${lang}] AI notice in footer and first-visit banner; dismiss persists`, async ({ page }) => {
      await open(page, lang, "/", { banner: true });
      await expect(page.getByTestId("ai-notice")).toBeVisible();
      await expect(page.getByTestId("ai-banner")).toBeVisible();
      await shot(page, `${lang}-banner`);
      await page.getByTestId("ai-banner-dismiss").click();
      await expect(page.getByTestId("ai-banner")).toHaveCount(0);
      await page.reload();
      await expect(page.getByTestId("ai-banner")).toHaveCount(0);
      await page.goto("/sources/");
      await expect(page.getByTestId("ai-banner")).toHaveCount(0);
    });

    test(`[${lang}] recent checks lists this session's items and a new session is empty`, async ({ page, browser }) => {
      await verifyText(page, lang, lang === "ar" ? "إنما الأعمال بالنيات" : "The reward of deeds depends upon the intentions");
      await verifyText(page, lang, lang === "ar" ? "حب الوطن من الإيمان" : "Love of the homeland is part of faith");
      await page.goto("/recent/");
      await expect(page.getByTestId("history-row")).toHaveCount(2);
      await shot(page, `${lang}-recent`);
      await page.getByTestId("history-row").first().getByRole("link").first().click();
      await expect(page.getByTestId("status-banner")).toBeVisible();
      await page.goto("/recent/");
      await page.getByTestId("clear-history").click();
      await expect(page.getByTestId("history-empty")).toBeVisible();
      await shot(page, `${lang}-recent-empty`);
      const ctx = await browser.newContext();
      const p2 = await ctx.newPage();
      await open(p2, lang, "/recent/");
      await expect(p2.getByTestId("history-empty")).toBeVisible();
      await ctx.close();
    });
  }

  // each chip's label is what the tool returns for it
  const CHIPS = { ar: [["ex1", ["verified"]], ["ex2", ["unreliable"]], ["ex3", ["unreliable"]]],
                  en: [["ex1", ["verified"]], ["ex2", ["unreliable"]], ["ex3", ["verified", "partial"]]] } as const;
  for (const lang of LANGS) {
    test(`[${lang}] example chips fill the input and run`, async ({ page }) => {
      for (const [key, expected] of CHIPS[lang]) {
        await open(page, lang);
        await page.getByTestId(`example-${key}`).click();
        await expect(page.getByTestId("input-text")).not.toHaveValue("");
        await page.getByTestId("verify-btn").click();
        await expect(page.getByTestId("status-banner")).toBeVisible({ timeout: 30_000 });
        expect(expected as readonly string[]).toContain(await state(page));
      }
    });
  }

  test("export report as PDF and request human review", async ({ page }) => {
    await verifyText(page, "ar", "إنما الأعمال بالنيات");
    await page.evaluate(() => { (window as unknown as { __printed: number }).__printed = 0; window.print = () => { (window as unknown as { __printed: number }).__printed++; }; });
    await page.getByTestId("pdf-btn").click();
    expect(await page.evaluate(() => (window as unknown as { __printed: number }).__printed)).toBe(1);
    await page.emulateMedia({ media: "print" });
    await expect(page.getByTestId("pdf-footer")).toBeVisible();
    await expect(page.getByTestId("ai-banner")).toBeHidden();
    await expect(page.getByTestId("pdf-btn")).toBeHidden();
    await page.emulateMedia({ media: "screen" });
    // the review request goes to the contact form (mocked here: tests never send real emails)
    const sent: Record<string, unknown>[] = [];
    await page.route("https://api.web3forms.com/submit", async (route) => {
      sent.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ success: true, message: "Email sent" }) });
    });
    await page.getByTestId("review-btn-aside").click();
    await expect(page.getByTestId("review-dialog")).toBeVisible();
    await page.getByTestId("review-name").fill("Test reviewer");
    await page.getByTestId("review-email").fill("not-an-email");
    await page.getByTestId("review-submit").click();
    await expect(page.getByTestId("review-error")).toBeVisible();
    expect(sent).toHaveLength(0);
    await page.getByTestId("review-email").fill("reviewer@example.com");
    await page.getByTestId("review-submit").click();
    await expect(page.getByTestId("review-sent")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("review-dialog")).toBeHidden();
    await expect(page.getByTestId("review-btn-aside")).toBeDisabled();
    expect(sent).toHaveLength(1);
    const form = sent[0] as { access_key: string; name: string; email: string; subject: string; message: string; botcheck: boolean };
    expect(form.access_key).toBeTruthy();
    expect([form.name, form.email, form.botcheck]).toEqual(["Test reviewer", "reviewer@example.com", false]);
    expect(form.message).toContain("إنما الأعمال بالنيات");
    // the PDF was generated by the server from its own report and is reachable from the link in the message
    const pdfUrl = (await page.getByTestId("review-pdf-link").getAttribute("href")) || "";
    expect(form.message).toContain(pdfUrl);
    const pdf = await page.request.get(pdfUrl);
    expect(pdf.status()).toBe(200);
    expect(pdf.headers()["content-type"]).toBe("application/pdf");
    expect((await pdf.body()).subarray(0, 5).toString()).toBe("%PDF-");
  });

  test("review dialog closes with Escape and nothing is sent", async ({ page }) => {
    await verifyText(page, "ar", "إنما الأعمال بالنيات");
    let calls = 0;
    await page.route("https://api.web3forms.com/submit", (route) => { calls++; return route.abort(); });
    await page.getByTestId("review-btn-aside").click();
    await expect(page.getByTestId("review-dialog")).toBeVisible();
    await expect(page.getByTestId("review-name")).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("review-dialog")).toBeHidden();
    await expect(page.getByTestId("review-btn-aside")).toBeEnabled();
    expect(calls).toBe(0);
  });

  test("narrations list the same report in other books, and the share image downloads", async ({ page }) => {
    await verifyText(page, "ar", "إنما الأعمال بالنيات");
    await expect(page.getByTestId("narrations-card")).toBeVisible();
    expect(await page.getByTestId("narration").count()).toBeGreaterThan(2);
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("share-btn").click()]);
    expect(download.suggestedFilename()).toMatch(/\.png$/);
    await download.saveAs(path.join(SHOTS, "share-card-ar.png"));
    await expect(page.getByTestId("share-btn")).toContainText("حُفظت");
  });

  test("share image in English for a fabricated saying", async ({ page }) => {
    await verifyText(page, "en", "Seek knowledge even if you have to go to China");
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("share-btn").click()]);
    await download.saveAs(path.join(SHOTS, "share-card-en.png"));
  });

  test("AI explanation block is labelled and separated when an LLM provider is configured", async ({ page, request }) => {
    const h = await (await request.get(`${API}/health`)).json();
    test.skip(!h.llm, "no LLM provider configured on the stack");
    await open(page, "ar", "/", { explain: true });
    await page.getByTestId("input-text").fill("إنما الأعمال بالنيات");
    await page.getByTestId("verify-btn").click();
    await expect(page.getByTestId("status-banner")).toBeVisible({ timeout: 45_000 });
    const card = page.getByTestId("ai-explanation");
    await expect(card).toBeVisible();
    await expect(card).toContainText("شرح مولَّد بالذكاء الاصطناعي");
    // any provider of the chain may answer when an earlier one is out of quota; a fixed wording is labelled "template"
    await expect(card).toContainText(new RegExp([...h.llm_chain, "template"].join("|")));
    // separated from the quoted source text: the explanation is not inside the grading or diff cards
    await expect(page.getByTestId("grade-card").getByTestId("ai-explanation")).toHaveCount(0);
    await shot(page, "ar-ai-explanation");
    // the language dropdown re-words the same facts in another language without re-verifying
    const before = await card.locator("p").innerText();
    await page.getByTestId("ai-lang").selectOption("fr");
    await expect(card.locator("p")).not.toHaveText(before, { timeout: 45_000 });
    await expect(card.locator("p")).toHaveText(/[A-Za-zéèàç]{3,}/, { timeout: 45_000 });
    await expect(page.getByTestId("status-banner")).toHaveAttribute("data-state", "verified");  // verdict untouched
    await shot(page, "ar-ai-explanation-fr");
    // extended mode: meaning / vocabulary / lessons of the matched text, with its own warning label
    await page.getByTestId("ai-lang").selectOption("ar");
    await page.getByTestId("ai-mode-extended").click();
    await expect(card).toHaveAttribute("data-mode", "extended");
    // grounded in الدرر السنية: either a summary with its source link, or an explicit "no source" notice — never free text
    await expect(card.getByTestId("ai-text").or(card.getByTestId("ai-no-source"))).toBeVisible({ timeout: 60_000 });
    await expect(card).toContainText("شرح موسّع مولَّد بالذكاء الاصطناعي");
    if (await card.getByTestId("ai-text").isVisible()) {
      await expect(card.getByTestId("ai-grounding")).toContainText("الدرر السنية");
      await expect(card.getByTestId("ai-grounding").locator("a")).toHaveAttribute("href", /dorar\.net\/(hadith|tafseer)/);
      expect((await card.getByTestId("ai-text").innerText()).length).toBeGreaterThan(300);
    }
    await expect(page.getByTestId("status-banner")).toHaveAttribute("data-state", "verified");
    await shot(page, "ar-ai-explanation-extended");
  });

  test("sources page renders in both languages", async ({ page }) => {
    await open(page, "ar", "/sources/");
    await expect(page.locator("h1")).toContainText("المصادر والمنهجية");
    await shot(page, "ar-sources");
    await page.getByTestId("lang-en").click();
    await expect(page.locator("h1")).toContainText("Sources & methodology");
    await shot(page, "en-sources");
  });
});
