// Dev helper: node scripts/screenshot.mjs <outdir> — full-page screenshots of every screen/state.
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const out = process.argv[2] || "shots";
const base = process.env.BASE || "http://localhost:3000";
mkdirSync(out, { recursive: true });
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true, args: ["--no-sandbox"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
await page.evaluateOnNewDocument(() => { try { localStorage.setItem("tahqaq.banner.dismissed", "1"); } catch {} });

const q = (t) => encodeURIComponent(t);
const shots = [
  ["home", "/"],
  ["sources", "/sources/"],
  ["recent-empty", "/recent/"],
  ["result-partial", `/result/?id=s1&text=${q("إنما الأعمال بالنية ولكل امرئ ما نوى")}`],
  ["result-verified", `/result/?id=s2&text=${q("حب الوطن من الإيمان")}`],
  ["result-uncertain", `/result/?id=s3&text=${q("النظافة من الإيمان")}`],
  ["result-abstain", `/result/?id=s4&text=${q("من قرأ هذا الدعاء ونشره بين عشرة أشخاص فُرّج همّه في يومه")}`],
  ["result-referral", `/result/?id=s5&text=${q("هل يجوز لي الجمع بين الصلاتين في السفر؟")}`],
  ["result-translation", `/result/?id=s6&text=${q("None of you is a Muslim until he loves for his brother what he loves for himself.")}`],
  ["result-quran", `/result/?id=s7&text=${q("قال رسول الله: وقل ربي زدني علما")}`],
  ["recent", "/recent/"],
];
for (const [name, path] of shots) {
  await page.goto(base + path, { waitUntil: "networkidle0", timeout: 60000 });
  if (path.startsWith("/result")) {
    await page.waitForFunction(() => !!document.querySelector("aside section"), { timeout: 60000 }).catch(() => {});
    await new Promise((r) => setTimeout(r, 400));
  }
  await page.screenshot({ path: `${out}/${name}.png`, fullPage: true });
  console.log("shot", name);
}
if (process.env.EN) {
  await page.evaluateOnNewDocument(() => { try { localStorage.setItem("tahqaq.lang", "en"); } catch {} });
  for (const [name, path] of shots.slice(0, 4)) {
    await page.goto(base + path, { waitUntil: "networkidle0", timeout: 60000 });
    if (path.startsWith("/result")) await page.waitForFunction(() => !!document.querySelector("aside section"), { timeout: 60000 }).catch(() => {});
    await page.screenshot({ path: `${out}/${name}-en.png`, fullPage: true });
    console.log("shot", name + "-en");
  }
}
await browser.close();
