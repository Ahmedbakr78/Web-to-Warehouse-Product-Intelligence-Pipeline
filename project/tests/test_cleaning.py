"""Unit tests for the cleaning / normalisation engine (no database required)."""

from __future__ import annotations

import pytest

from app.ingestion.cleaning import (
    clean_brand,
    clean_product_name,
    collapse_whitespace,
    content_hash,
    convert_to_usd,
    detect_currency_locale,
    format_price,
    is_valid_price,
    is_valid_rating,
    normalise_availability,
    normalise_category,
    normalise_currency,
    normalise_name_key,
    normalise_unicode,
    parse_number,
    parse_price,
    parse_rating,
    percent_change,
    validate_url,
)


# --------------------------------------------------------------------------------------
# Product names
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  SALE: Apple iPhone 15 Pro (256GB) - Titanium ", "Apple iPhone 15 Pro - Titanium"),
        ("<b>HP Pavilion</b> 15 Laptop, 16GB RAM", "HP Pavilion 15 Laptop 16GB RAM"),
        ("New!!! Sony \u201cWH-1000XM5\u201d Headphones", "Sony WH-1000XM5 Headphones"),
        ("New Balance 574 Sneakers", "New Balance 574 Sneakers"),
        ("NEW Samsung Galaxy S24", "Samsung Galaxy S24"),
        ("", ""),
        (None, ""),
    ],
)
def test_clean_product_name(raw, expected):
    assert clean_product_name(raw) == expected


def test_clean_product_name_truncates_on_word_boundary():
    long_name = "Product " * 200
    cleaned = clean_product_name(long_name, max_length=40)
    assert len(cleaned) <= 40
    assert not cleaned.endswith("Produc")


def test_normalise_name_key_ignores_noise_words():
    left = normalise_name_key("The Great Gatsby (Hardcover)")
    right = normalise_name_key("great gatsby")
    assert left == right == "gatsby great"


def test_normalise_name_key_sorts_tokens():
    assert normalise_name_key("256GB iPhone Apple") == normalise_name_key("Apple iPhone 256GB")


def test_normalise_unicode_folds_smart_punctuation():
    assert normalise_unicode("\u201cQuoted\u201d \u2014 dash") == '"Quoted" - dash'


def test_collapse_whitespace():
    assert collapse_whitespace("  a \n\t b   c ") == "a b c"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Sony", "Sony"),
        ("  by Sony  ", "Sony"),
        ("Brand: LG", "LG"),
        ("the", None),
        ("", None),
        (None, None),
    ],
)
def test_clean_brand(raw, expected):
    assert clean_brand(raw) == expected


# --------------------------------------------------------------------------------------
# Prices and currencies
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "amount", "currency"),
    [
        ("$1,234.56", 1234.56, "USD"),
        ("\u20ac12,99", 12.99, "EUR"),
        ("\u00a345.90", 45.90, "GBP"),
        ("USD 89.99", 89.99, "USD"),
        ("\u20b91,499", 1499.0, "INR"),
        ("1.234,56 EUR", 1234.56, "EUR"),
        ("Price: $7", 7.0, "USD"),
    ],
)
def test_parse_price_variants(raw, amount, currency):
    info = parse_price(raw)
    assert info.amount == pytest.approx(amount)
    assert info.currency == currency
    assert info.confidence >= 0.6


def test_parse_price_range_uses_midpoint():
    info = parse_price("$10 - $20")
    assert info.is_range is True
    assert info.amount == pytest.approx(15.0)
    assert (info.range_low, info.range_high) == (10.0, 20.0)


def test_parse_price_prefers_current_price_over_was_price():
    info = parse_price("Was $49.99 Now $39.99")
    assert info.amount == pytest.approx(39.99)
    assert info.matched_pattern == "was_now"


@pytest.mark.parametrize("raw", ["Free", "N/A", "", None, "call for price", "--"])
def test_parse_price_handles_non_numeric(raw):
    info = parse_price(raw)
    assert info.amount is None
    assert info.is_valid is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1,234.56", 1234.56),
        ("1.234,56", 1234.56),
        ("1 234,56", 1234.56),
        ("45,90", 45.90),
        ("1,499", 1499.0),
        ("12", 12.0),
        ("abc", None),
        (None, None),
    ],
)
def test_parse_number(raw, expected):
    assert parse_number(raw) == pytest.approx(expected) if expected is not None else parse_number(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$", "USD"),
        ("USD", "USD"),
        ("\u20ac", "EUR"),
        ("\u00a3", "GBP"),
        ("R$", "BRL"),
        ("jpy", "JPY"),
        ("", None),
    ],
)
def test_normalise_currency(raw, expected):
    assert normalise_currency(raw) == expected


def test_normalise_currency_finds_symbol_in_text():
    assert normalise_currency("Now 39.99 GBP only") == "GBP"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://shop.example.co.uk/item", "GBP"),
        ("https://x.de/item", "EUR"),
        ("https://x.com/item", None),
    ],
)
def test_detect_currency_locale_from_url(url, expected):
    assert detect_currency_locale(None, url) == expected


def test_convert_to_usd_uses_reference_table():
    amount, rate = convert_to_usd(100.0, "EUR")
    assert rate == pytest.approx(1.0865)
    assert amount == pytest.approx(108.65, abs=0.01)


def test_convert_to_usd_unknown_currency_is_pass_through():
    amount, rate = convert_to_usd(50.0, "XYZ")
    assert (amount, rate) == (50.0, 1.0)


def test_format_price_uses_symbol_and_thousands():
    assert format_price(1234.5, "USD").startswith("$")
    assert "1,234" in format_price(1234.5, "USD")
    assert format_price(None) == "\u2014"


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [(100.0, 110.0, 10.0), (100.0, 90.0, -10.0), (0.0, 10.0, 100.0), (None, 10.0, None), (10.0, 0.0, -100.0)],
)
def test_percent_change(old, new, expected):
    assert percent_change(old, new) == pytest.approx(expected)


def test_is_valid_price_and_rating():
    assert is_valid_price(10.5) is True
    assert is_valid_price(-1) is False
    assert is_valid_price(None) is False
    assert is_valid_rating(4.2) is True
    assert is_valid_rating(9.9) is False


# --------------------------------------------------------------------------------------
# Ratings and availability
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("4.5 out of 5", 4.5),
        ("82%", 4.1),
        ("3.8/5", 3.8),
        ("4.0", 4.0),
    ],
)
def test_parse_rating_normalises_scale(raw, expected):
    info = parse_rating(raw)
    assert info.value == pytest.approx(expected, abs=0.01)


def test_parse_rating_extracts_count():
    info = parse_rating("4.5 out of 5", count_text="based on 1,204 ratings")
    assert info.count == 1204


def test_parse_rating_missing():
    assert parse_rating(None).value is None
    assert parse_rating("").value is None


@pytest.mark.parametrize(
    ("raw", "status", "in_stock"),
    [
        ("Add to cart", "in_stock", True),
        ("In stock", "in_stock", True),
        ("Currently unavailable", "out_of_stock", False),
        ("Sold out", "out_of_stock", False),
        ("Pre-order", "preorder", False),
        ("Only 2 left", "limited_stock", True),
        ("???", "unknown", False),
        (None, "unknown", False),
    ],
)
def test_normalise_availability(raw, status, in_stock):
    assert normalise_availability(raw) == (status, in_stock)


def test_availability_flag_overrides_text():
    assert normalise_availability("anything", in_stock_flag=False) == ("out_of_stock", False)


# --------------------------------------------------------------------------------------
# Categories
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("electronics > mobile phones", "Electronics > Mobile Phones"),
        ("Books", "Books"),
        ("Books / Textbooks", "Books > Textbooks"),
        ("mens clothing", "Apparel > Men"),
        ("unknown", "Uncategorised"),
        (None, "Uncategorised"),
        ("   ", "Uncategorised"),
    ],
)
def test_normalise_category(raw, expected):
    assert normalise_category(raw) == expected


def test_content_hash_is_stable_and_discriminating():
    assert content_hash("a", "b") == content_hash("a", "b")
    assert content_hash("a", "b") != content_hash("a", "c")


@pytest.mark.parametrize(
    ("url", "valid"),
    [("https://example.com/p", True), ("http://x.y", True), ("ftp://x.y", False), ("", False), (None, False)],
)
def test_validate_url(url, valid):
    assert validate_url(url) is valid
