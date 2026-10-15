"""Team catalogue: weights sum to 100 and the lead owns the most functions."""

from __future__ import annotations

from app.core.team import TEAM, team


def test_weights_sum_to_100():
    assert sum(m["weight"] for m in TEAM) == 100
    assert team()["total_weight"] == 100


def test_lead_is_ahmed_with_most_functions():
    catalogue = team()
    assert catalogue["lead"] == "Ahmedbakr78"
    lead = next(m for m in catalogue["members"] if m["lead"])
    assert lead["member"] == "Ahmed (78102)"
    assert lead["weight"] == max(m["weight"] for m in catalogue["members"])
    assert len(lead["functions"]) >= max(len(m["functions"]) for m in catalogue["members"] if not m["lead"])


def test_every_member_has_github_role_and_functions():
    for member in TEAM:
        assert member["github"] and member["github_url"].endswith(member["github"])
        assert member["role"] and member["component"]
        assert len(member["functions"]) >= 4
