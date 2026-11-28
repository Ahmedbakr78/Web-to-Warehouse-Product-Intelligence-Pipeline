"""Ingestion: compliance-aware HTTP access, cleaning, normalisation and deduplication.

`base` also owns the source registry (`register_source`, `get_source`,
`list_sources`) - there is no separate `registry` module.
"""

__all__ = [
    "base",
    "cleaning",
    "compliance",
    "dedupe",
    "http_client",
    "ratelimit",
    "robots",
    "sources",
]
