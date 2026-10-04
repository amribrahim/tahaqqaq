"""Generate the synthetic voice benchmark with the macOS speech voices (Arabic: Majed, English: Daniel, French: Eddy).
Items: authentic hadiths from the corpus benchmark read in Arabic, published English translations, and negative cases
(silence, French, noise) that must be refused. Audio goes to qa/voice/ (local, not published); labels to voice.jsonl.
Usage (macOS): python -m eval.voice.make_voice"""
from __future__ import annotations

import json
import random
import struct
import subprocess
import wave
from pathlib import Path

from app import db
from app.normalize import strip_tashkeel

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[2] / "qa" / "voice"


def say(voice: str, text: str, path: Path) -> None:
    aiff = path.with_suffix(".aiff")
    subprocess.run(["say", "-v", voice, "-o", str(aiff), text], check=True)
    subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", str(aiff), str(path)], check=True)
    aiff.unlink()


def wav(path: Path, seconds: float, noise: float) -> None:
    rng = random.Random(7)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        frames = b"".join(struct.pack("<h", int(rng.uniform(-1, 1) * noise * 32767)) for _ in range(int(16000 * seconds)))
        w.writeframes(frames)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    bench = [json.loads(x) for x in (HERE.parent / "benchmark.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    arabic = [b for b in bench if b["group"] == "sahih_exact"][:20]
    items = []
    for i, b in enumerate(arabic, 1):
        f = OUT / f"ar{i:02d}.m4a"
        text = strip_tashkeel(b["text"])
        say("Majed", text, f)
        items.append({"file": f.name, "lang": "ar", "text": text, "expect_record": b["expect_record"]})
    with db.get_conn() as conn:
        rows = conn.execute("SELECT collection, number, text_en FROM texts WHERE collection = 'bukhari' AND text_en <> '' "
                            "AND length(text_en) BETWEEN 60 AND 260 ORDER BY md5('voice' || number) LIMIT 10").fetchall()
    for i, r in enumerate(rows, 1):
        f = OUT / f"en{i:02d}.m4a"
        text = r["text_en"].split(":", 1)[-1].strip() if r["text_en"].lower().startswith("narrated") else r["text_en"]
        say("Daniel", text, f)
        items.append({"file": f.name, "lang": "en", "text": text, "expect_record": [[r["collection"], r["number"]]]})
    say("Eddy (French (France))", "Le Prophète a dit : les actions ne valent que par les intentions.", OUT / "neg_french.m4a")
    wav(OUT / "neg_silence.wav", 3, 0.0)
    wav(OUT / "neg_noise.wav", 3, 0.25)
    items += [{"file": "neg_french.m4a", "expect_error": "stt_language"},
              {"file": "neg_silence.wav", "expect_error": "stt_no_speech"},
              {"file": "neg_noise.wav", "expect_error": "stt_no_speech|stt_unclear|stt_language"}]
    (HERE / "voice.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in items) + "\n", encoding="utf-8")
    print(len(items), "items in", OUT)


if __name__ == "__main__":
    main()
