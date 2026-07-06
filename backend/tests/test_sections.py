"""Filing section carving — table-of-contents entries and inline
cross-references must not be mistaken for (or truncate) real sections."""

from app.extraction.sections import carve_sections, find_section

FAKE_10K = "\n".join(
    [
        "UNITED STATES SECURITIES AND EXCHANGE COMMISSION",
        "TABLE OF CONTENTS",
        "Item 1. Business",  # ToC entry (tiny span)
        "3",
        "Item 1A. Risk Factors",  # ToC entry
        "48",
        "Item 7. Management's Discussion and Analysis",
        "82",
        "Part I",
        "Item 1. Business",  # real section start
        "We are a company. " * 300,
        "For more detail see Item 1A. Risk Factors below.",  # inline cross-ref (mid-line)
        "More business content. " * 300,
        "Item 1A. Risk Factors",  # real section start
        "Risk one is bad. " * 400,
        "Item 1B. Unresolved Staff Comments",
        "None.",
        "Item 7. Management's Discussion and Analysis",  # real MD&A
        "Revenues went up. " * 400,
        "Item 8. Financial Statements",
        "numbers " * 50,
    ]
)


def test_business_section_is_body_not_toc():
    sections = carve_sections(FAKE_10K, "10-K")
    assert "Business" in sections
    assert len(sections["Business"]) > 5_000  # the real section, not the ToC line
    assert "We are a company." in sections["Business"]


def test_risk_factors_not_truncated_by_inline_cross_reference():
    sections = carve_sections(FAKE_10K, "10-K")
    risk = sections["Risk Factors"]
    assert "Risk one is bad." in risk
    # the inline "see Item 1A..." cross-reference must not have started the
    # section early, and the section must run all the way to Item 1B
    assert len(risk) > 5_000


def test_mdna_found_and_ends_at_item_8():
    sections = carve_sections(FAKE_10K, "10-K")
    mdna = sections["MD&A"]
    assert "Revenues went up." in mdna
    assert "Financial Statements" not in mdna


def test_missing_sections_fall_back_to_leading_slice():
    sections = carve_sections("Just some text with no item headers at all.", "10-K")
    assert sections == {"Document": "Just some text with no item headers at all."}


def test_find_section_returns_empty_on_no_match():
    assert find_section("nothing here", r"^item\s+1a\.", [r"^item\s+2\."]) == ""
