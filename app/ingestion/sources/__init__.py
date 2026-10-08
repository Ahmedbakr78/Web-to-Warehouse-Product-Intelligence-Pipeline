"""Concrete ingestion sources (free, public, automation-permitted endpoints).

Importing this package registers every source with the global registry.
"""

from __future__ import annotations

from app.ingestion.sources import (  # noqa: F401
    books_to_scrape,
    dummyjson,
    fakestore,
    google_books,
    local_fixture,
    openfoodfacts_prices,
    openlibrary,
    scrapeme,
    steam_store,
)

__all__ = [
    "books_to_scrape",
    "dummyjson",
    "fakestore",
    "google_books",
    "local_fixture",
    "openfoodfacts_prices",
    "openlibrary",
    "scrapeme",
    "steam_store",
]
