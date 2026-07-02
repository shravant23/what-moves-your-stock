"""Carve the relevant sections out of filing text.

A 10-K is ~700K characters, most of it financial statements and exhibits.
Extraction only needs Business, Risk Factors, and MD&A. Headers appear twice
(table of contents + body), so for each section we take the candidate span
with the greatest length — the ToC entry is followed almost immediately by
the next item header, the real section by tens of thousands of characters."""

import re

# (start_pattern, [end_patterns]). Patterns are anchored to line starts (^)
# so inline cross-references ("see Item 3.") neither start nor truncate a
# section, and allow newlines inside headers ("Item 1A. \nRisk Factors.").
SECTIONS_10K: dict[str, tuple[str, list[str]]] = {
    "Business": (
        r"^item[s]?\s+1\.\s*(?:and\s+2\.\s*)?[\s\S]{0,60}?business",
        [r"^item\s+1a\.", r"^item\s+3\."],
    ),
    "Risk Factors": (
        r"^item\s+1a\.[\s\S]{0,40}?risk\s+factors",
        [r"^item\s+1b\.", r"^item\s+2\.", r"^item\s+3\."],
    ),
    "MD&A": (
        r"^item[s]?\s+7\.[\s\S]{0,200}?management",
        [r"^item\s+8\.", r"^item\s+9\."],
    ),
}

SECTIONS_10Q: dict[str, tuple[str, list[str]]] = {
    "MD&A": (
        r"^item\s+2\.[\s\S]{0,40}?management",
        [r"^item\s+3\.", r"^item\s+4\."],
    ),
    "Risk Factors": (
        r"^item\s+1a\.[\s\S]{0,40}?risk\s+factors",
        [r"^item\s+2\.", r"^item\s+5\.", r"^item\s+6\."],
    ),
}

_FLAGS = re.IGNORECASE | re.MULTILINE


def find_section(text: str, start_pat: str, end_pats: list[str]) -> str:
    """Longest span from a start-header match to the nearest following
    end-header match. The table-of-contents occurrence of a header yields a
    tiny span, the body occurrence a huge one — longest wins.
    Returns "" if the section can't be located."""
    best = ""
    for m in re.finditer(start_pat, text, _FLAGS):
        end_positions = []
        for ep in end_pats:
            em = re.search(ep, text[m.end():], _FLAGS)
            if em:
                end_positions.append(m.end() + em.start())
        end = min(end_positions) if end_positions else len(text)
        span = text[m.start():end]
        if len(span) > len(best):
            best = span
    return best.strip()


def carve_sections(text: str, form: str, caps: dict[str, int] | None = None) -> dict[str, str]:
    """{section_name -> text} for the sections extraction cares about.
    Falls back to a leading slice of the whole document if nothing matched."""
    caps = caps or {}
    spec = SECTIONS_10K if form == "10-K" else SECTIONS_10Q
    out: dict[str, str] = {}
    for name, (start_pat, end_pats) in spec.items():
        section = find_section(text, start_pat, end_pats)
        cap = caps.get(name, 200_000)
        if section:
            out[name] = section[:cap]
    if not out:
        out["Document"] = text[:250_000]
    return out
