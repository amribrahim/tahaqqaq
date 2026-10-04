import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// The assistant widget: limited scope, verification through chat, voice with a confirmation step, clear errors.
// The microphone is a generated tone (getUserMedia returns a real MediaStream from an oscillator), so MediaRecorder and
// the loudness meter run as with a real device on any machine; /api/stt is intercepted so the voice flow is deterministic.
async function fakeMicrophone(page: Page, volume = 0.3) {
  await page.addInitScript((v) => {
    navigator.mediaDevices.getUserMedia = async () => {
      const ctx = new AudioContext();
      await ctx.resume();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      gain.gain.value = v;
      const dest = ctx.createMediaStreamDestination();
      osc.frequency.value = 440;
      osc.connect(gain).connect(dest);
      osc.start();
      return dest.stream;
    };
  }, volume);
}

async function openAssistant(page: Page, lang: "ar" | "en", path = "/") {
  await page.addInitScript((l) => {
    localStorage.setItem("tahqaq.lang", l);
    localStorage.setItem("tahqaq.banner.dismissed", "1");
    localStorage.setItem("tahqaq.explain", "0");
  }, lang);
  await page.goto(path);
  await page.getByTestId("assistant-open").click();
  await expect(page.getByTestId("assistant-panel")).toBeVisible();
  await expect(page.getByTestId("assistant-input")).toBeFocused();
}

async function ask(page: Page, text: string) {
  const before = await page.getByTestId("assistant-bot").count();
  await page.getByTestId("assistant-input").fill(text);
  await page.getByTestId("assistant-send").click();
  await expect(page.getByTestId("assistant-bot")).toHaveCount(before + 1, { timeout: 30_000 });
  return page.getByTestId("assistant-bot").last();
}

test("verifies a hadith in the chat and opens the full report", async ({ page }) => {
  await openAssistant(page, "ar");
  const reply = await ask(page, "هل يصح حديث إنما الأعمال بالنيات");
  await expect(reply.getByTestId("assistant-state")).toHaveAttribute("data-state", "verified");
  await expect(reply).toContainText("صحيح البخاري");
  await reply.getByTestId("assistant-report-link").click();
  await expect(page.getByTestId("status-banner")).toHaveAttribute("data-state", "verified");
});

test("flags a fabricated saying with its quoted ruling", async ({ page }) => {
  await openAssistant(page, "ar");
  const reply = await ask(page, "حب الوطن من الإيمان");
  await expect(reply.getByTestId("assistant-state")).toHaveAttribute("data-state", "unreliable");
  await expect(reply).toContainText("موضوع");
});

test("stays in scope: refuses other topics and fatwas, answers about the tool", async ({ page }) => {
  await openAssistant(page, "en");
  await expect(await ask(page, "Who won the world cup?")).toContainText("hadith");
  await expect(await ask(page, "ما حكم صلاة الجماعة في المسجد؟")).toContainText("فتوى");
  await expect(await ask(page, "ما مصادر الأداة؟")).toContainText("الدرر");
});

test("explains the report open on the page", async ({ page }) => {
  await page.addInitScript(() => { localStorage.setItem("tahqaq.banner.dismissed", "1"); localStorage.setItem("tahqaq.explain", "0"); });
  await page.goto(`/result/?id=asst-ctx&text=${encodeURIComponent("إنما الأعمال بالنيات")}`);
  await expect(page.getByTestId("status-banner")).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("assistant-open").click();
  const reply = await ask(page, "لماذا هذه النتيجة؟");
  await expect(reply).toContainText("صحيح");               // the recorded ruling, never a different one
  await expect(reply).not.toContainText("ضعيف");
});

test("voice: the transcript is confirmed before anything is verified", async ({ page }) => {
  await fakeMicrophone(page);
  await page.route("**/api/stt", (route) => route.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ text: "قال رسول الله صلى الله عليه وسلم إنما الأعمال بالنيات", lang: "ar", duration: 3.1, confidence: 92 }) }));
  await openAssistant(page, "ar");
  await page.getByTestId("assistant-mic").click();
  await expect(page.getByTestId("assistant-mic")).toHaveAttribute("aria-pressed", "true");
  await page.waitForTimeout(1800);
  await page.getByTestId("assistant-mic").click();
  await expect(page.getByTestId("assistant-confirm")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("assistant-transcript")).toContainText("إنما الأعمال بالنيات");
  expect(await page.getByTestId("assistant-user").count()).toBe(0);          // nothing sent before confirmation
  await page.getByTestId("assistant-confirm-send").click();
  await expect(page.getByTestId("assistant-bot").last().getByTestId("assistant-state")).toHaveAttribute("data-state", "verified", { timeout: 30_000 });
});

test("voice: an unclear or unsupported recording gives a clear error, never a guess", async ({ page }) => {
  await fakeMicrophone(page);
  await page.route("**/api/stt", (route) => route.fulfill({ status: 422, contentType: "application/json",
    body: JSON.stringify({ detail: { code: "stt_language", message: "الصوت متاح بالعربية والإنجليزية فقط. اكتب النص بدلًا من ذلك." } }) }));
  await openAssistant(page, "ar");
  await page.getByTestId("assistant-mic").click();
  await page.waitForTimeout(1800);
  await page.getByTestId("assistant-mic").click();
  const err = page.getByTestId("assistant-bot").last();
  await expect(err).toHaveAttribute("role", "alert", { timeout: 15_000 });
  await expect(err).toContainText("العربية والإنجليزية فقط");
  await expect(page.getByTestId("assistant-confirm")).toHaveCount(0);
});

test("voice: a silent recording is refused in the browser and nothing is uploaded", async ({ page }) => {
  await fakeMicrophone(page, 0);
  let uploads = 0;
  await page.route("**/api/stt", (route) => { uploads++; return route.fulfill({ status: 200, body: "{}" }); });
  await openAssistant(page, "ar");
  await page.getByTestId("assistant-mic").click();
  await page.waitForTimeout(1800);
  await page.getByTestId("assistant-mic").click();
  const err = page.getByTestId("assistant-bot").last();
  await expect(err).toHaveAttribute("role", "alert", { timeout: 15_000 });
  await expect(err).toContainText("لم أسمع صوتًا");
  expect(uploads).toBe(0);
});

test("keyboard: Escape closes the panel and returns focus to the button", async ({ page }) => {
  await openAssistant(page, "en");
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("assistant-panel")).toHaveCount(0);
  await expect(page.getByTestId("assistant-open")).toBeFocused();
});

for (const lang of ["ar", "en"] as const) {
  test(`[${lang}] the open assistant has no WCAG 2.1 AA violations`, async ({ page }) => {
    await openAssistant(page, lang);
    await ask(page, lang === "ar" ? "ما مصادر الأداة؟" : "What are the sources?");
    const res = await new AxeBuilder({ page }).include("#assistant-panel").withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(res.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(" | ")}`)).toEqual([]);
  });
}
