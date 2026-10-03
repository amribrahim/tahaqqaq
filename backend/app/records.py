from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Grade:
    grader_ar: str
    grader_en: str
    grade_ar: str      # verbatim as recorded in the source
    grade_en: str
    source_ar: str
    source_en: str
    number: str = ""
    url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class Record:
    id: int
    kind: str
    collection: str
    book_ar: str
    book_en: str
    number: str
    chapter_ar: str
    chapter_en: str
    text_ar: str
    matn_ar: str
    matn_norm: str
    text_en: str
    text_en_norm: str
    type_ar: str
    type_en: str
    grades: list[dict[str, Any]]
    source_url: str
    alt_url: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
    # populated by searches
    semantic: float = 0.0   # cosine of the best window
    lexical: float = 0.0    # trigram word_similarity (0-1)
    stage: str = ""         # exact | trigram | semantic | none

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Record:
        return cls(
            id=row["id"], kind=row["kind"], collection=row["collection"], book_ar=row["book_ar"],
            book_en=row["book_en"], number=row["number"], chapter_ar=row["chapter_ar"],
            chapter_en=row["chapter_en"], text_ar=row["text_ar"], matn_ar=row["matn_ar"],
            matn_norm=row["matn_norm"], text_en=row["text_en"], text_en_norm=row["text_en_norm"],
            type_ar=row["type_ar"], type_en=row["type_en"], grades=row["grades"] or [],
            source_url=row["source_url"], alt_url=row.get("alt_url") or "", meta=row.get("meta") or {},
            semantic=float(row.get("semantic") or 0.0), lexical=float(row.get("lexical") or 0.0),
        )


@dataclass
class GlossaryTerm:
    term_ar: str
    term_en: str
    meaning_en: str
    meaning_ar: str
    avoid: list[str]
    note_ar: str = ""
    note_en: str = ""
    source_url: str = ""
