# Benchmark — تحقّق

98 labelled inputs, run against `http://localhost:8000` with the optional AI steps off.

Expected records include every record that carries the same wording (the Six Books repeat hadiths across numbers and books).

| Group | n | Accuracy (state + record) | Wrong attributions |
|---|---|---|---|
| sahih_exact | 30 | 97% | 1 |
| sahih_variant | 30 | 93% | 2 |
| fabricated_or_weak | 12 | 100% | 0 |
| ayah_exact | 10 | 100% | 0 |
| ayah_misquoted | 5 | 100% | 0 |
| invented | 6 | 100% | 0 |
| fatwa | 5 | 100% | 0 |

**Overall accuracy: 97%** · **wrong attributions: 3 / 98** (3.1%) · abstain on invented texts: 6/6 · median latency 301.5 ms

## Misses

- [sahih_exact] `اشتكت النار إلى ربها فقالت يا رب أكل بعضي بعضا فأذن لها بنفسين نفس في ` → got verified ['bukhari', '536'] (95%), expected ['verified'] [['muslim', '617a']]
- [sahih_variant] `«حدثني أبو الربيع، وأبو كامل قالا حدثنا حماد، - وهو ابن زيد - عن أيوب،` → got verified ['ibnmajah', '1151'] (100%), expected ['verified', 'partial'] [['muslim', '169f']]
- [sahih_variant] `لغدةو في سبيل الله أو روحة خير من الدنيا وما فيها` → got verified ['bukhari', '6415'] (99%), expected ['verified', 'partial'] [['bukhari', '2792'], ['muslim', '1880']]
