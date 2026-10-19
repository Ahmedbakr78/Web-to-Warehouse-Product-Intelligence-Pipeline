"""Tests for the fuzzy duplicate detector (pure, no database required)."""

from __future__ import annotations

import pytest

from app.ingestion.cleaning import blocking_key, name_fingerprint, normalise_name_key
from app.ingestion.dedupe import (
    DedupeEngine,
    combined_similarity,
    digit_signature,
    digit_signature_factor,
    jaro,
    jaro_winkler,
    levenshtein,
    token_set_ratio,
    trigram_similarity,
)

#: (name_a, name_b, must_be_duplicate) - the golden set for the matcher.
DUPLICATE_PAIRS = [
    ("Apple iPhone 15 Pro 256GB", "Apple iPhone 15 Pro 256 GB", True),
    ("Sony WH-1000XM5 Wireless Headphones", "Sony WH1000XM5 Wireless Headphone", True),
    ("Logitech MX Master 3S", "Logitech MX Master 3", True),
    ("SAMSUNG Galaxy S23 128GB Black", "Samsung Galaxy S23 128 GB Black", True),
    ("The Great Gatsby", "The Great Gatsby (Hardcover)", True),
    ("Amazon Basics USB-C Cable 2m", "Amazon Basics USB C Cable 2 m", True),
    ("Sony Bravia XR A1 65 inch OLED", 'Sony Bravia XR A1 65" OLED TV', True),
    ("HP Pavilion 15 Laptop 16GB RAM", "HP Pavilion 15 Laptop, 16GB RAM", True),
    # --- must stay distinct -------------------------------------------------------
    ("HP Pavilion 15 Laptop", "HP Pavilion 15 Notebook", False),
    ("Dell XPS 13", "Acer Aspire 5", False),
    ("Adidas Mens Running Shoes Size 10", "Adidas Womens Running Shoes Size 9", False),
    ("Canon EOS R6 Mark II Camera", "Canon EOS R5 Mark II Camera", False),
    ("Sony WH-1000XM5", "Sony WH-1000XM4", False),
    ("The Great Gatsby", "Gone With The Wind", False),
    ("Nike Air Zoom Pegasus 40", "Nike Air Zoom Pegasus 39", False),
]

THRESHOLD = 0.90


# --------------------------------------------------------------------------------------
# Primitive measures
# --------------------------------------------------------------------------------------
def test_levenshtein_basic():
    assert levenshtein("kitten", "sitting") == 3
    assert levenshtein("same", "same") == 0
    assert levenshtein("", "abc") == 3


def test_levenshtein_early_abandonment():
    assert levenshtein("abcdefgh", "zzzzzzzz", max_distance=2) > 2


def test_jaro_winkler_rewards_common_prefix():
    assert jaro_winkler("martha", "marhta") > jaro("martha", "marhta")
    assert jaro_winkler("abc", "abc") == pytest.approx(1.0)
    assert 0 <= jaro("abc", "xyz") <= 1


def test_token_set_ratio_ignores_extra_words():
    assert token_set_ratio("red running shoe", "running shoe") > 0.85
    assert token_set_ratio("cat", "dog") < 0.4


def test_trigram_similarity_bounds():
    assert trigram_similarity("dinner", "dinner") == pytest.approx(1.0)
    assert trigram_similarity("abc", "xyz") < 0.4


def test_digit_signature_captures_model_numbers():
    assert digit_signature("iPhone 15 Pro 256GB") == ("15", "256")
    assert digit_signature("Canon EOS R6") == ("6",)


def test_digit_signature_factor_penalises_different_models():
    assert digit_signature_factor(("6",), ("5",)) == 0.85
    assert digit_signature_factor(("6", "2"), ("5", "1")) == 0.60
    assert digit_signature_factor(("6",), ("6",)) == 1.0
    assert digit_signature_factor((), ("5",)) == 1.0


# --------------------------------------------------------------------------------------
# Combined similarity
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize(("name_a", "name_b", "expected"), DUPLICATE_PAIRS)
def test_combined_similarity_golden_set(name_a, name_b, expected):
    score, parts = combined_similarity(name_a, name_b)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0
    assert (score >= THRESHOLD) is expected, f"{name_a!r} vs {name_b!r} scored {score}"
    assert parts, "the breakdown must always be returned for explainability"


def test_combined_similarity_identical_names_score_one():
    score, _ = combined_similarity("Bose QuietComfort 45", "Bose QuietComfort 45")
    assert score == pytest.approx(1.0)


def test_combined_similarity_empty_input():
    assert combined_similarity("", "Something")[0] == 0.0
    assert combined_similarity(None or "", "x")[0] == 0.0


def test_brand_mismatch_reduces_score():
    strong, _ = combined_similarity("Alpha Widget 2000", "Alpha Widget 2000")
    mixed, _ = combined_similarity("Alpha Widget 2000", "Alpha Widget 2000", brand_a="Alpha", brand_b="Beta")
    assert mixed < strong


# --------------------------------------------------------------------------------------
# Keys and blocking
# --------------------------------------------------------------------------------------
def test_fingerprint_is_stable_and_brand_aware():
    assert name_fingerprint("Sony WH-1000XM5", "Sony") == name_fingerprint("Sony WH-1000XM5", "Sony")
    assert name_fingerprint("Sony WH-1000XM5", "Sony") != name_fingerprint("Sony WH-1000XM5", "Bose")


def test_blocking_key_is_prefix_of_name_key():
    key = normalise_name_key("Samsung Galaxy S23 128GB Black")
    assert blocking_key("Samsung Galaxy S23 128GB Black", 4) == key[:4]
    assert blocking_key("", 4) == ""


# --------------------------------------------------------------------------------------
# Engine behaviour without a database
# --------------------------------------------------------------------------------------
def test_engine_duplicate_discovery_within_a_batch():
    engine = DedupeEngine(session=None, threshold=0.9)  # type: ignore[arg-type]
    found = engine.duplicates_in_iterable(
        [
            "Apple iPhone 15 Pro 256GB",
            "Apple iPhone 15 Pro 256 GB",
            "Canon EOS R6 Mark II Camera",
            "Canon EOS R5 Mark II Camera",
        ]
    )
    assert len(found) == 1
    assert found[0][2] >= 0.9


def test_engine_stats_track_work():
    engine = DedupeEngine(session=None, threshold=0.9)  # type: ignore[arg-type]
    engine.duplicates_in_iterable(["A B", "A B", "C D"])
    stats = engine.stats.as_dict()
    assert stats["examined"] >= 0
    assert "merged" in stats and "new_products" in stats
