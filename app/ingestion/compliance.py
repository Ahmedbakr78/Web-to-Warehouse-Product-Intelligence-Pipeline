"""Data-quality, ethical web-ingestion and data-preparation layer.

The pipeline only ever reads from sources that are explicitly allow-listed for
automated access (their ``robots.txt`` permits the relevant user-agents and their
terms of service allow programmatic access).  Nothing in this package bypasses a
paywall, a login, a CAPTCHA or a ``Disallow`` directive.
"""

__all__: list[str] = []
