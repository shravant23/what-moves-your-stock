"""Citation verification (acceptance test 9.1).

Every citation's quote is string-matched against the actual filing text after
whitespace/punctuation normalization. Exposures whose citations all fail are
rejected — a hallucinated quote never reaches the UI."""

import re

from pydantic import BaseModel

from ..models import Citation, ExposureProfile

_TRANSLATE = str.maketrans(
    {
        "‘": "'", "’": "'",  # curly single quotes
        "“": '"', "”": '"',  # curly double quotes
        "–": "-", "—": "-",  # en/em dashes
        " ": " ",  # non-breaking space
        "­": "",  # soft hyphen
    }
)


def normalize(s: str) -> str:
    s = s.translate(_TRANSLATE).lower()
    return re.sub(r"\s+", " ", s).strip()


class VerificationReport(BaseModel):
    citations_checked: int = 0
    citations_verified: int = 0
    citations_rejected: int = 0
    exposures_kept: int = 0
    exposures_dropped: list[str] = []  # names of exposures with no valid citation
    rejected_quotes: list[str] = []


class Verifier:
    def __init__(self, docs: dict[str, str]):
        """docs: {source_doc label -> full filing text}"""
        self._norm_docs = {label: normalize(text) for label, text in docs.items()}

    def citation_ok(self, citation: Citation) -> bool:
        quote = normalize(citation.quote).strip('"\'')
        if not quote:
            return False
        # Prefer the named source doc, but accept a match in any provided doc
        # (the model occasionally mislabels which filing a quote came from).
        named = self._norm_docs.get(citation.source_doc)
        if named is not None and quote in named:
            return True
        return any(quote in text for text in self._norm_docs.values())

    def verify_profile(self, profile: ExposureProfile) -> tuple[ExposureProfile, VerificationReport]:
        """Return a cleaned profile (hallucinated citations removed, unsupported
        exposures dropped) and a report of what happened."""
        report = VerificationReport()

        def check(citation: Citation | None) -> Citation | None:
            if citation is None:
                return None
            report.citations_checked += 1
            if self.citation_ok(citation):
                report.citations_verified += 1
                return citation
            report.citations_rejected += 1
            report.rejected_quotes.append(citation.quote)
            return None

        kept_exposures = []
        for exposure in profile.exposures:
            verified = [c for c in exposure.citations if check(c) is not None]
            if verified:
                exposure = exposure.model_copy(update={"citations": verified})
                kept_exposures.append(exposure)
            else:
                report.exposures_dropped.append(exposure.name)

        segments = [
            s.model_copy(update={"citation": check(s.citation)})
            for s in profile.revenue_segments
        ]
        regions = [
            g.model_copy(update={"citation": check(g.citation)})
            for g in profile.geographic_mix
        ]
        debt = profile.debt_profile.model_copy(
            update={"citation": check(profile.debt_profile.citation)}
        )

        report.exposures_kept = len(kept_exposures)
        cleaned = profile.model_copy(
            update={
                "exposures": kept_exposures,
                "revenue_segments": segments,
                "geographic_mix": regions,
                "debt_profile": debt,
            }
        )
        return cleaned, report
