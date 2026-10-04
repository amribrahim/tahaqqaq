/** Which script a text is written in, for the instant check before verifying: Arabic texts are verified in the
 *  Arabic interface and English texts in the English one. The API makes the full check (it also tells English from
 *  other Latin-script languages); this only catches the obvious mismatch without a round trip. Arabic honorifics
 *  inside an English translation («Muhammad صلى الله عليه وسلم») do not make it Arabic. */
const HONORIFICS = /ﷺ|صلى الله عليه و ?سلم|رضي الله عنه(?:ما|م|ا)?|عليه(?:م|ا)? السلام|سبحانه وتعالى|عز وجل|جل جلاله/g;

export function scriptOf(text: string): "ar" | "en" | null {
  const t = text.replace(HONORIFICS, " ");
  const ar = (t.match(/[ء-يٱ-ۓ]/g) || []).length;
  const la = (t.match(/[A-Za-z]/g) || []).length;
  if (ar === 0 && la === 0) return null;
  return ar >= 0.6 * la ? "ar" : "en";
}
