"""Concrete ingestion sources (free, public, automation-permitted endpoints).

Importing this package registers every source with the global registry.
"""

from __future__ import annotations

from app.ingestion.sources import (  # noqa: F401
    bitstamp,
    books_to_scrape,
    cheapshark,
    coincap,
    coingecko,
    dummyjson,
    fakestore,
    google_books,
    gutendex,
    itunes,
    itunes_ebooks,
    kraken,
    local_fixture,
    makeup,
    mmobomb,
    openfoodfacts_prices,
    openlibrary,
    platzi,
    pokemontcg,
    restful_objects,
    scrapeme,
    scryfall,
    steam_store,
    stooq,
    ygoprodeck,
)

__all__ = [
    "bitstamp",
    "books_to_scrape",
    "cheapshark",
    "coincap",
    "coingecko",
    "dummyjson",
    "fakestore",
    "google_books",
    "gutendex",
    "itunes",
    "itunes_ebooks",
    "kraken",
    "local_fixture",
    "makeup",
    "mmobomb",
    "openfoodfacts_prices",
    "openlibrary",
    "platzi",
    "pokemontcg",
    "restful_objects",
    "scrapeme",
    "scryfall",
    "steam_store",
    "stooq",
    "ygoprodeck",
]
