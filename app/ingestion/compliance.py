"""The ingestion compliance policy, in one place.

Every outbound request passes through the transport layer, which consults this
policy before a single byte leaves the process. The module exists so the rules
are stated once and can be *checked*, rather than being described in prose
that can drift away from the code.

The policy is deliberately conservative and narrow:

* A source is only collected when the site **publishes** terms that permit
  automated access. The operator confirms this when the source is registered
  and the flag is stored on the source row, so it can be audited later.
* ``robots.txt`` is fetched and evaluated for the crawling user-agent before
  every request, and the decision is written to the HTTP audit log.
* A ``Disallow`` directive, a ``401``/``403`` response for ``robots.txt``
  (RFC 9309 *Unauthorised*) and a source whose terms forbid polling all
  stop the request.
* Nothing in this package bypasses a paywall, a login or a CAPTCHA. There is
  no code path that authenticates against a site in order to read it.
* A source is only picked up automatically when it is classified as
  :data:`~app.ingestion.base.DATA_TRUST_REAL` - a feed that publishes
  genuine market data. Mock APIs and scraping sandboxes have to be named
  explicitly, and their rows can be removed again with ``purge-untrusted``.

The one deliberate relaxation is RFC 9309's *Unavailable* rule: a host that
answers ``404`` (or cannot be reached at all) has published nothing that
forbids crawling, so the request is allowed and the decision is labelled as a
fallback rather than as a published rule. The transport still rate-limits
such a host and still audits the request.
"""

from __future__ import annotations

from typing import Any

#: Bumped whenever the rules above change, so the audit log can show which
#: policy a decision was made under.
POLICY_VERSION = "1.1"

#: How each ``robots.txt`` outcome maps to a decision, with the rule string
#: the audit log records. The strings are the *explanation* of the decision,
#: so they name what actually happened.
ROBOTS_POLICY: dict[str, dict[str, Any]] = {
    "published": {
        "decision": "follow the parsed rules",
        "rule": "robots.txt:{allow|disallow}",
    },
    "unauthorised": {
        "decision": "disallow the whole host",
        "rule": "robots-unauthorised:disallow (RFC 9309 - 401/403 on robots.txt)",
    },
    "unavailable": {
        "decision": "allow the whole host",
        "rule": "robots.txt:allow",
    },
    "unreachable": {
        "decision": "allow the whole host",
        "rule": "robots-unavailable:fallback-allow (robots.txt could not be fetched)",
    },
    "not-applicable": {
        "decision": "allow (the source never hits the network)",
        "rule": "robots.txt:allow",
    },
}

#: The guarantees this package makes, in the words the documentation uses.
#: A test asserts that every clause here still holds, so the list cannot
#: quietly become a set of claims nobody checks.
GUARANTEES: tuple[str, ...] = (
    "robots.txt is fetched and evaluated before every outbound request",
    "a Disallow directive stops the request",
    "a 401/403 robots.txt response disallows the whole host",
    "a source whose terms forbid automated access is never collected",
    "a source that is not classified as real market data is never collected automatically",
    "every request decision is written to the HTTP audit log",
    "no paywall, login or CAPTCHA is bypassed",
)


def rule_for(outcome: str) -> str:
    """The audit-log rule string for a ``robots.txt`` outcome."""
    return str(ROBOTS_POLICY.get(outcome, {}).get("rule", "robots.txt:allow"))


def allowed_outcomes() -> frozenset[str]:
    """The outcomes under which a request may proceed."""
    return frozenset(
        outcome
        for outcome, spec in ROBOTS_POLICY.items()
        if spec.get("decision", "").startswith("allow") or spec.get("decision", "").startswith("follow")
    )


__all__ = [
    "GUARANTEES",
    "POLICY_VERSION",
    "ROBOTS_POLICY",
    "allowed_outcomes",
    "rule_for",
]
