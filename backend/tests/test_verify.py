"""Citation verifier — the anti-hallucination guarantee (spec 9.1)."""

from app.extraction.verify import Verifier, normalize
from app.models import Citation

from .conftest import make_citation, make_exposure, make_profile

DOCS = {
    "TST 10-K FY2025": (
        "Item 1A. Risk Factors.\n"
        "We mine copper in Indonesia and our results vary with copper prices.\n"
        "Energy represented 15% of our operating costs — including “diesel”.\n"
    )
}


def test_normalize_collapses_whitespace_and_unicode():
    assert normalize("We  MINE\n copper") == "we mine copper"
    assert normalize("“diesel”") == '"diesel"'
    assert normalize("a–b — c") == "a-b - c"


def test_exact_quote_verifies():
    v = Verifier(DOCS)
    assert v.citation_ok(make_citation("We mine copper in Indonesia"))


def test_quote_with_different_whitespace_and_curly_quotes_verifies():
    v = Verifier(DOCS)
    assert v.citation_ok(make_citation('including "diesel"'))
    assert v.citation_ok(make_citation("results  vary with\ncopper prices"))


def test_paraphrased_quote_is_rejected():
    v = Verifier(DOCS)
    assert not v.citation_ok(make_citation("Our copper mining results fluctuate with market prices"))


def test_mislabeled_source_doc_falls_back_to_any_doc():
    v = Verifier(DOCS)
    c = Citation(source_doc="TST 10-Q 2026-03-31", section="MD&A", quote="We mine copper in Indonesia")
    assert v.citation_ok(c)


def test_empty_quote_is_rejected():
    v = Verifier(DOCS)
    assert not v.citation_ok(make_citation(""))


def test_verify_profile_drops_unsupported_exposure_and_keeps_verified():
    good = make_exposure(name="Copper Prices", quote="our results vary with copper prices")
    bad = make_exposure(name="Invented Exposure", quote="this quote appears nowhere at all")
    profile = make_profile([good, bad])

    cleaned, report = Verifier(DOCS).verify_profile(profile)

    assert [e.name for e in cleaned.exposures] == ["Copper Prices"]
    assert report.exposures_kept == 1
    assert report.exposures_dropped == ["Invented Exposure"]
    assert report.citations_checked == 2
    assert report.citations_verified == 1
    assert report.citations_rejected == 1
    assert "nowhere" in report.rejected_quotes[0]


def test_verify_profile_strips_only_bad_citation_when_another_supports():
    exposure = make_exposure(quote="our results vary with copper prices")
    exposure.citations.append(make_citation("totally fabricated quote"))
    cleaned, report = Verifier(DOCS).verify_profile(make_profile([exposure]))

    assert len(cleaned.exposures) == 1
    assert len(cleaned.exposures[0].citations) == 1
    assert report.citations_rejected == 1
