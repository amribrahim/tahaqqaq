"""Classify a verbatim ruling into a display family. The ruling text itself is never changed."""
from __future__ import annotations

import re

_MAWDU = re.compile(r"موضوع|باطل|لا أصل|لا اصل|منكر|ليس بثابت|ليس بصحيح|ليس بحديث|ليس حديثا|ليس له أصل|ليس له إسناد|"
                    r"لم أجد|لم يرد|لا يصح|لم يصح|لا يثبت|لم يثبت|غير صحيح|غير محفوظ|لا يعرف له|لا يعرف في|كذب|كذاب|"
                    r"مكذوب|وضاع|ليس من كلام|تالف")
_DAIF = re.compile(r"ضعيف|ضعف|واه|متروك")
_SAHIH = re.compile(r"صحيح")
_HASAN = re.compile(r"حسن")


def grade_family(grade_ar: str) -> str:
    g = grade_ar or ""
    if "آية" in g:
        return "ayah"
    if _MAWDU.search(g):
        return "mawdu"
    if _DAIF.search(g):
        return "daif"
    if _SAHIH.search(g):
        return "sahih"
    if _HASAN.search(g):
        return "hasan"
    return "other"


def is_unreliable(grade_ar: str) -> bool:
    """True when the scholars' recorded ruling means the text must not be attributed as authentic."""
    return grade_family(grade_ar) in ("mawdu", "daif")
