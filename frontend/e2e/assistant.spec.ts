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

async function openAssistant(page: Page, lang: "ar" | "en", path = "/", voice = false) {
  await page.addInitScript(({ l, v }) => {
    localStorage.setItem("tahqaq.assistant.voice", v ? "1" : "0");   // spoken replies off unless the test is about them
    localStorage.setItem("tahqaq.lang", l);
    localStorage.setItem("tahqaq.banner.dismissed", "1");
    localStorage.setItem("tahqaq.explain", "0");
  }, { l: lang, v: voice });
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

// -- voice conversation ---------------------------------------------------------------------------------
async function burstyMicrophone(page: Page) {
  // speaks in bursts (1.2 s of tone, 2 s of silence), so end-of-speech detection runs as with a person
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = async () => {
      const ctx = new AudioContext();
      await ctx.resume();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      gain.gain.value = 0;
      const dest = ctx.createMediaStreamDestination();
      osc.connect(gain).connect(dest);
      osc.start();
      let on = false;
      const flip = () => { on = !on; gain.gain.value = on ? 0.3 : 0; setTimeout(flip, on ? 1200 : 2000); };
      setTimeout(flip, 2000);
      return dest.stream;
    };
  });
}

async function fakeVoices(page: Page, transcripts: string[]) {
  let n = 0;
  await page.route("**/api/stt", (route) => {
    const text = transcripts[Math.min(n++, transcripts.length - 1)];
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ text, lang: "ar", duration: 2, confidence: 95 }) });
  });
  // a tiny valid WAV for every spoken sentence (the real voice is generated by the server)
  const wav = Buffer.alloc(44 + 1600);
  wav.write("RIFF", 0); wav.writeUInt32LE(36 + 1600, 4); wav.write("WAVE", 8); wav.write("fmt ", 12); wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22); wav.writeUInt32LE(8000, 24); wav.writeUInt32LE(16000, 28); wav.writeUInt16LE(2, 32);
  wav.writeUInt16LE(16, 34); wav.write("data", 36); wav.writeUInt32LE(1600, 40);
  await page.route("**/api/tts", (route) => route.fulfill({ status: 200, contentType: "audio/wav", body: wav }));
}

test("voice call: hears a hadith, reads it back, verifies after a spoken yes, answers aloud", async ({ page }) => {
  test.setTimeout(90_000);
  await burstyMicrophone(page);
  await fakeVoices(page, ["قال رسول الله صلى الله عليه وسلم إنما الأعمال بالنيات", "نعم"]);
  await openAssistant(page, "ar");
  await page.getByTestId("voice-call-start").click();
  await expect(page.getByTestId("voice-call")).toBeVisible();
  await expect(page.getByTestId("voice-heard")).toContainText("إنما الأعمال بالنيات", { timeout: 30_000 });
  await expect(page.getByTestId("voice-answer")).toContainText("صحيح البخاري", { timeout: 40_000 });
  await page.getByTestId("voice-call-end").click();
  await expect(page.getByTestId("voice-call")).toHaveCount(0);
  await expect(page.getByTestId("assistant-bot").last().getByTestId("assistant-state")).toHaveAttribute("data-state", "verified");
});

test("voice call: a spoken no means nothing is verified and the assistant asks again", async ({ page }) => {
  test.setTimeout(90_000);
  await burstyMicrophone(page);
  await fakeVoices(page, ["إنما الأعمال بالنيات وإنما لكل امرئ ما نوى", "لا"]);
  let asked = 0;
  page.on("request", (r) => { if (r.url().endsWith("/api/assistant") && !(r.postData() || "").includes("route_only\":true")) asked++; });
  await openAssistant(page, "ar");
  await page.getByTestId("voice-call-start").click();
  await expect(page.getByTestId("voice-heard")).toContainText("إنما الأعمال", { timeout: 30_000 });
  await expect(page.getByTestId("voice-phase")).toHaveText(/أستمع|قل نعم|أتحدث/, { timeout: 30_000 });
  await page.waitForTimeout(6000);
  expect(asked).toBe(0);                                   // a «لا» never leads to a verification
  await page.getByTestId("voice-call-end").click();
});

test("the voice call screen has no WCAG 2.1 AA violations", async ({ page }) => {
  await burstyMicrophone(page);
  await fakeVoices(page, ["إنما الأعمال بالنيات وإنما لكل امرئ ما نوى", "نعم"]);
  await openAssistant(page, "ar");
  await page.getByTestId("voice-call-start").click();
  await expect(page.getByTestId("voice-heard")).toBeVisible({ timeout: 30_000 });
  const res = await new AxeBuilder({ page }).include("#assistant-panel").withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(res.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(" | ")}`)).toEqual([]);
  await page.getByTestId("voice-call-end").click();
});

test("Sanad greets aloud on the first open of a session, once", async ({ page }) => {
  const spoken: string[] = [];
  await page.route("**/api/tts", async (route) => {
    spoken.push(JSON.parse(route.request().postData() || "{}").text);
    await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: { code: "tts_unavailable" } }) });
  });
  await openAssistant(page, "ar", "/", true);
  await expect.poll(() => spoken.join(" ")).toContain("أنا سند");
  await expect.poll(() => spoken.join(" "), { timeout: 20_000 }).toContain("نتحقق منه");   // the whole greeting, sentence by sentence
  await expect(page.getByTestId("assistant-open")).toContainText("سند");
  const n = spoken.length;
  await page.getByTestId("assistant-close").click();
  await page.getByTestId("assistant-open").click();
  await page.waitForTimeout(800);
  expect(spoken.length).toBe(n);                                   // no second greeting in the same session
  await expect(await ask(page, "كيف حالك؟")).toContainText("بخير");
});

test("New conversation empties the chat and Sanad greets again", async ({ page }) => {
  const spoken: string[] = [];
  await page.route("**/api/tts", async (route) => {
    spoken.push(JSON.parse(route.request().postData() || "{}").text);
    await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: { code: "tts_unavailable" } }) });
  });
  await openAssistant(page, "ar", "/", true);
  await expect.poll(() => spoken.join(" "), { timeout: 20_000 }).toContain("نتحقق منه");
  await ask(page, "كيف حالك؟");
  expect(await page.getByTestId("assistant-user").count()).toBe(1);
  const before = spoken.filter((x) => x.includes("أنا سند")).length;
  await page.getByTestId("assistant-new").click();
  await expect(page.getByTestId("assistant-user")).toHaveCount(0);
  await expect(page.getByTestId("assistant-bot")).toHaveCount(0);
  await expect(page.getByTestId("assistant-log")).toContainText("أنا سند");          // the welcome is back
  await expect(page.getByTestId("assistant-input")).toBeFocused();
  await expect.poll(() => spoken.filter((x) => x.includes("أنا سند")).length, { timeout: 20_000 }).toBeGreaterThan(before);
  await page.reload();
  await page.getByTestId("assistant-open").click();
  await expect(page.getByTestId("assistant-user")).toHaveCount(0);                    // the cleared chat stays cleared
});
