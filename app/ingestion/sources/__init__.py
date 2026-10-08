"""Concrete ingestion sources (free, public, automation-permitted endpoints).

Importing this package registers every source with the global registry.
"""

from __future__ import annotations

from app.ingestion.sources import (  # noqa: F401
    books_to_scrape,
    cheapshark,
    dummyjson,
    fakestore,
    google_books,
    gutendex,
    itunes,
    kraken,
    local_fixture,
    makeup,
    mmobomb,
    openfoodfacts_prices,
    openlibrary,
    platzi,
    scrapeme,
    steam_store,
    ygoprodeck,
)

__all__ = [
    "books_to_scrape",
    "cheapshark",
    "dummyjson",
    "fakestore",
    "google_books",
    "gutendex",
    "itunes",
    "kraken",
    "local_fixture",
    "makeup",
    "mmobomb",
    "openfoodfacts_prices",
    "openlibrary",
    "platzi",
    "scrapeme",
    "steam_store",
    "ygoprodeck",
]
