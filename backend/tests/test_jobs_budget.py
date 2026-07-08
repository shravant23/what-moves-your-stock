"""Daily analysis budget for public-demo instances."""

from app.jobs import analyses_used_today, consume_analysis_budget


def test_budget_starts_at_zero_and_increments():
    start = analyses_used_today()
    consume_analysis_budget()
    consume_analysis_budget()
    assert analyses_used_today() == start + 2
