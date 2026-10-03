/** A shareable image of a verification result (1080×1350, the portrait size social networks show in full).
 *  Drawn on a canvas with the page's own fonts; Arabic shaping and RTL come from the browser's text engine.
 *  It carries only what the report says: the state, the recorded ruling and its source, never a verdict of our own. */
import type { Report } from "./api";
import { STATE } from "./tokens";

export type ShareLabels = { brand: string; tagline: string; stateLbl: string; stateLabel: string; input: string; ruling: string; source: string; footer: string; site: string };

function wrap(ctx: CanvasRenderingContext2D, text: string, maxWidth: number, maxLines: number): string[] {
  const words = text.replace(/\s+/g, " ").trim().split(" ");
  const lines: string[] = [];
  let line = "";
  for (const w of words) {
    const next = line ? `${line} ${w}` : w;
    if (ctx.measureText(next).width > maxWidth && line) {
      lines.push(line);
      line = w;
      if (lines.length === maxLines) break;
    } else {
      line = next;
    }
  }
  if (lines.length < maxLines && line) lines.push(line);
  if (lines.length === maxLines && words.join(" ").length > lines.join(" ").length) lines[maxLines - 1] = lines[maxLines - 1].replace(/\s*\S*$/, " …");
  return lines;
}

function fontFamily(selector: string, fallback: string): string {
  const el = document.querySelector(selector) ?? document.body;
  return getComputedStyle(el).fontFamily || fallback;
}

export async function drawShareCard(r: Report, lang: "ar" | "en", L: ShareLabels): Promise<Blob> {
  await document.fonts?.ready;
  const W = 1080, H = 1350, P = 80;
  const c = document.createElement("canvas");
  c.width = W; c.height = H;
  const ctx = c.getContext("2d")!;
  const rtl = lang === "ar";
  const head = fontFamily(".font-cairo", "sans-serif");
  const body = fontFamily("body", "sans-serif");
  const st = STATE[r.state];
  ctx.direction = rtl ? "rtl" : "ltr";
  ctx.textAlign = rtl ? "right" : "left";
  const x = rtl ? W - P : P;

  // background and header band
  ctx.fillStyle = "#0d1035"; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = st.color; ctx.fillRect(0, 0, W, 14);
  ctx.fillStyle = "#ffffff"; ctx.font = `800 64px ${head}`; ctx.fillText(L.brand, x, P + 70);
  ctx.fillStyle = "#c9c3ff"; ctx.font = `500 30px ${body}`; ctx.fillText(L.tagline, x, P + 120);

  // state block
  let y = P + 210;
  const sx = rtl ? W - P - 40 : P + 40;
  ctx.fillStyle = st.surface.replace(/[\d.]+\)$/, "0.22)");
  ctx.beginPath(); ctx.roundRect(P, y, W - 2 * P, 150, 28); ctx.fill();
  ctx.fillStyle = st.color; ctx.font = `700 28px ${body}`; ctx.fillText(L.stateLbl, sx, y + 52);
  ctx.fillStyle = "#ffffff"; ctx.font = `800 48px ${head}`;
  ctx.fillText(wrap(ctx, `${st.glyph}  ${L.stateLabel}`, W - 2 * P - 80, 1)[0] ?? "", sx, y + 115);

  // the text as the user shared it
  y += 210;
  ctx.fillStyle = "#9d97d6"; ctx.font = `700 28px ${body}`; ctx.fillText(L.input, x, y);
  ctx.fillStyle = "#ffffff"; ctx.font = `600 40px ${head}`;
  const inputDir = /[؀-ۿ]/.test(r.input_text) ? "rtl" : "ltr";
  ctx.direction = inputDir; ctx.textAlign = inputDir === "rtl" ? "right" : "left";
  const ix = inputDir === "rtl" ? W - P : P;
  for (const line of wrap(ctx, `«${r.input_text}»`, W - 2 * P, 6)) { y += 64; ctx.fillText(line, ix, y); }
  ctx.direction = rtl ? "rtl" : "ltr"; ctx.textAlign = rtl ? "right" : "left";

  // recorded ruling and source
  if (r.grade && r.state !== "abstain" && r.state !== "referral") {
    y += 90;
    ctx.fillStyle = "#9d97d6"; ctx.font = `700 28px ${body}`; ctx.fillText(L.ruling, x, y);
    y += 58; ctx.fillStyle = st.color; ctx.font = `800 44px ${head}`;
    const g = rtl ? `${r.grade.grade_ar} — ${r.grade.grader_ar}` : `${r.grade.grade_en || r.grade.grade_ar} — ${r.grade.grader_en || r.grade.grader_ar}`;
    ctx.fillText(wrap(ctx, g, W - 2 * P, 1)[0] ?? "", x, y);
    y += 70; ctx.fillStyle = "#9d97d6"; ctx.font = `700 28px ${body}`; ctx.fillText(L.source, x, y);
    y += 54; ctx.fillStyle = "#e4e1ff"; ctx.font = `600 36px ${body}`;
    const src = r.source ? (rtl ? `${r.grade.source_ar || r.source.book_ar} · ${r.grade.number || r.source.number}` : `${r.grade.source_en || r.source.book_en} · ${r.grade.number || r.source.number}`) : "";
    ctx.fillText(wrap(ctx, src, W - 2 * P, 1)[0] ?? "", x, y);
  }

  // footer: disclaimer and address
  ctx.fillStyle = "rgba(201,195,255,0.25)"; ctx.fillRect(P, H - 220, W - 2 * P, 2);
  ctx.fillStyle = "#c9c3ff"; ctx.font = `500 26px ${body}`;
  let fy = H - 170;
  for (const line of wrap(ctx, L.footer, W - 2 * P, 2)) { ctx.fillText(line, x, fy); fy += 40; }
  ctx.fillStyle = "#3ee6c0"; ctx.font = `700 32px ${body}`; ctx.fillText(L.site, x, H - 70);

  return await new Promise<Blob>((resolve, reject) => c.toBlob((b) => (b ? resolve(b) : reject(new Error("canvas"))), "image/png"));
}

/** On phones, share through the system sheet when the browser can share files; elsewhere download the PNG. */
export async function shareOrDownload(blob: Blob, filename: string, title: string): Promise<"shared" | "downloaded"> {
  const file = new File([blob], filename, { type: "image/png" });
  const nav = navigator as Navigator & { canShare?: (d: { files: File[] }) => boolean };
  const touch = typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;   // phones: system share sheet
  if (touch && nav.canShare?.({ files: [file] }) && nav.share) {
    try { await nav.share({ files: [file], title }); return "shared"; } catch { /* cancelled: fall back to a download */ }
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return "downloaded";
}
