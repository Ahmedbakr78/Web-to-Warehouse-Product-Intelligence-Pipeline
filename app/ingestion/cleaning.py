"""Cleaning, normalisation and enrichment.

All functions here are pure and deterministic so they can be unit tested without a
database or network.  They implement the "clean product names and categories +
normalise currencies/price formats" requirements of the brief:

* ``clean_product_name``  - unicode + whitespace + promotional-noise removal
* ``normalise_name_key``  - comparison key used for exact/fuzzy matching
* ``normalise_category``  - casing, hierarchy and synonym mapping
* ``parse_price``         - locale/currency aware price extraction
* ``normalise_currency``  - ISO-4217 resolution (symbol, code, text)
* ``parse_rating``        - "4.5 out of 5" -> 4.5, scale normalisation to /5
* ``normalise_availability`` - in_stock / out_of_stock / preorder / backorder
* ``detect_currency_locale`` - heuristic that resolves the currency of a page
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from app.core.logging import get_logger

log = get_logger(__name__)

# --------------------------------------------------------------------------------------
# Unicode / text normalisation
# --------------------------------------------------------------------------------------
_SMART_CHARS = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201a": "'",
    "\u201b": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u201e": '"',
    "\u201f": '"',
    "\u2013": "-",
    "\u2014": "-",
    "\u2015": "-",
    "\u2212": "-",
    "\u2026": "...",
    "\u00a0": " ",
    "\u200b": "",
    "\u200c": "",
    "\u200d": "",
    "\ufeff": "",
    "\u00ad": "",
}
_CHAR_MAP = {ord(k): v for k, v in _SMART_CHARS.items()}

#: Marketing noise stripped from the front of product titles.
#:
#: The set is split in two on purpose. ``STRONG_PREFIXES`` contain an explicit
#: marketing phrase (usually followed by a colon or dash) and are always removed.
#: ``WEAK_PREFIXES`` are ordinary English words that also appear inside real brand
#: names ("New Balance 574", "Top Gear"), so they are only removed when the source
#: shouted them - uppercase, or immediately followed by punctuation such as
#: "SALE!!!". Getting this wrong would silently corrupt product names, so the
#: conservative branch is the default.
STRONG_PREFIXES = (
    r"sale[:\-]",
    r"hot sale[:\-]",
    r"clearance[:\-]",
    r"special offer[:\-]",
    r"brand new[:\-]",
    r"new arrival",
    r"limited offer[:\-]",
    r"discount[:\-]",
    r"offer[:\-]",
    r"best price[:\-]",
    r"free shipping[:\-]",
    r"bestseller[:\-]",
    r"top rated[:\-]",
    r"recommended[:\-]",
    r"featured[:\-]",
    r"hot deal[:\-]",
    r"promo(?:tional)?[:\-]",
    r"cheap[:\-]",
    r"wholesale[:\-]",
    r"clearance",
)
WEAK_PREFIXES = r"new|sale|offer|special|hot|best|top|limited|discount|premium|deal"

_PROMO_PREFIX_RE = re.compile(rf"^(?:{'|'.join(STRONG_PREFIXES)})[\s\-]*\s+", re.IGNORECASE)
# Case-SENSITIVE on purpose: only an ALL-CAPS token (NEW/SALE/...) is noise.
_WEAK_PREFIX_ALLCAPS_RE = re.compile(
    rf"^(?:{'|'.join(word.upper() for word in WEAK_PREFIXES.split('|'))})\s+"
)
_WEAK_PREFIX_PUNCT_RE = re.compile(
    rf"^(?:{'|'.join(WEAK_PREFIXES.split('|'))})[\s\-]*[!.,:;]{{1,3}}\s+", re.IGNORECASE
)
_PROMO_SUFFIXES = (
    r"\(new\)",
    r"\[new\]",
    r"- new arrival",
    r"- free shipping",
    r"\(free shipping\)",
    r"- limited stock",
    r"\*\*",
    r"-?\s*hot sale",
    r"\d+% off",
)
_PROMO_SUFFIX_RE = re.compile(rf"(?:{'|'.join(_PROMO_SUFFIXES)})\s*$", re.IGNORECASE)

_WHITESPACE_RE = re.compile(r"\s+")
_MULTI_PUNCT_RE = re.compile(r"[!\"#$%&()\[\]{}+/\\:;?.,`^~|<>]+")
_BRACKETED_RE = re.compile(r"\((?:[^()]{0,40})\)|\[(?:[^\[\]]{0,40})\]")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WORD_RE = re.compile(r"[a-z0-9]+")

#: Words ignored when comparing product names (brand/model noise).
STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "for",
        "with",
        "in",
        "on",
        "by",
        "to",
        "new",
        "sale",
        "offer",
        "special",
        "free",
        "shipping",
        "edition",
        "pack",
        "set",
        "kit",
        "size",
        "colour",
        "color",
        "brand",
        "official",
        "genuine",
        "oem",
        "original",
        "hot",
        "best",
        "top",
        "quality",
        "premium",
        "plus",
        "pro",
        "max",
        "ultra",
        "deluxe",
        "hd",
        "uk",
        "us",
        "eu",
        "intl",
        # Format / edition qualifiers describe the same product in the retail sense.
        "hardcover",
        "hardback",
        "paperback",
        "softcover",
        "unabridged",
        "abridged",
        "anniversary",
        "collector",
        "remastered",
        "standard",
        "reissue",
        "reprint",
    }
)

# --------------------------------------------------------------------------------------
# Currency handling
# --------------------------------------------------------------------------------------
CURRENCY_SYMBOLS: dict[str, str] = {
    "$": "USD",
    "us$": "USD",
    "usd": "USD",
    "u.s.$": "USD",
    "€": "EUR",
    "eur": "EUR",
    "£": "GBP",
    "gbp": "GBP",
    "£s": "GBP",
    "¥": "JPY",
    "￥": "JPY",
    "jpy": "JPY",
    "cny": "CNY",
    "rmb": "CNY",
    "元": "CNY",
    "₹": "INR",
    "inr": "INR",
    "rs": "INR",
    "rs.": "INR",
    "₩": "KRW",
    "krw": "KRW",
    "₺": "TRY",
    "try": "TRY",
    "tl": "TRY",
    "₽": "RUB",
    "rub": "RUB",
    "₪": "ILS",
    "₫": "VND",
    "₱": "PHP",
    "php": "PHP",
    "zł": "PLN",
    "pln": "PLN",
    "kr": "SEK",
    "sek": "SEK",
    "chf": "CHF",
    "r$": "BRL",
    "brl": "BRL",
    "a$": "AUD",
    "aud": "AUD",
    "c$": "CAD",
    "cad": "CAD",
    "د.إ": "AED",
    "aed": "AED",
    "sar": "SAR",
    "﷼": "SAR",
    "egp": "EGP",
    "ج.م": "EGP",
    "₦": "NGN",
}

#: Offline reference FX rates (1 unit of currency = X USD). Documented as static so the
#: pipeline never depends on a paid FX API; ``normalize_currency_amount`` is the single
#: place to swap in a live provider.
STATIC_FX_RATES: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.0865,
    "GBP": 1.2712,
    "JPY": 0.00640,
    "CNY": 0.1400,
    "INR": 0.01200,
    "AUD": 0.6580,
    "CAD": 0.7320,
    "CHF": 1.1280,
    "SEK": 0.0950,
    "PLN": 0.2500,
    "TRY": 0.0290,
    "RUB": 0.0110,
    "BRL": 0.1820,
    "ZAR": 0.0545,
    "MXN": 0.0580,
    "SGD": 0.7450,
    "HKD": 0.1280,
    "KRW": 0.00073,
    "AED": 0.2723,
    "SAR": 0.2666,
    "EGP": 0.0208,
    "ILS": 0.2710,
    "PHP": 0.0175,
    "NGN": 0.00067,
}

CURRENCY_NAMES: dict[str, str] = {
    "USD": "US Dollar",
    "EUR": "Euro",
    "GBP": "British Pound",
    "JPY": "Japanese Yen",
    "CNY": "Chinese Yuan",
    "INR": "Indian Rupee",
    "AUD": "Australian Dollar",
    "CAD": "Canadian Dollar",
    "CHF": "Swiss Franc",
    "SEK": "Swedish Krona",
    "PLN": "Polish Zloty",
    "TRY": "Turkish Lira",
    "RUB": "Russian Ruble",
    "BRL": "Brazilian Real",
    "ZAR": "South African Rand",
    "MXN": "Mexican Peso",
    "SGD": "Singapore Dollar",
    "HKD": "Hong Kong Dollar",
    "KRW": "South Korean Won",
    "AED": "UAE Dirham",
    "SAR": "Saudi Riyal",
    "EGP": "Egyptian Pound",
    "ILS": "Israeli Shekel",
    "PHP": "Philippine Peso",
    "NGN": "Nigerian Naira",
}

CURRENCY_SYMBOL_OUT = {
    "USD": "$",
    "EUR": "\u20ac",
    "GBP": "\u00a3",
    "JPY": "\u00a5",
    "CNY": "\u00a5",
    "INR": "\u20b9",
    "AUD": "A$",
    "CAD": "C$",
    "TRY": "\u20ba",
    "RUB": "\u20bd",
    "BRL": "R$",
    "PLN": "z\u0142",
    "SEK": "kr",
    "CHF": "CHF",
}

# --------------------------------------------------------------------------------------
# Category normalisation
# --------------------------------------------------------------------------------------
#: Lower-case synonym -> canonical category (industry agnostic but retail oriented).
CATEGORY_SYNONYMS: dict[str, str] = {
    # electronics
    "electronics": "Electronics",
    "electronic": "Electronics",
    "tech": "Electronics",
    "technology": "Electronics",
    "gadgets": "Electronics",
    "consumer electronics": "Electronics",
    "computers": "Electronics > Computers",
    "computer": "Electronics > Computers",
    "laptops": "Electronics > Computers",
    "laptop": "Electronics > Computers",
    "notebooks": "Electronics > Computers",
    "desktops": "Electronics > Computers",
    "mobile phones": "Electronics > Mobile Phones",
    "smartphones": "Electronics > Mobile Phones",
    "smart phone": "Electronics > Mobile Phones",
    "cell phones": "Electronics > Mobile Phones",
    "tablets": "Electronics > Tablets",
    "tablet": "Electronics > Tablets",
    "headphones": "Electronics > Audio",
    "audio": "Electronics > Audio",
    "speakers": "Electronics > Audio",
    "cameras": "Electronics > Photography",
    "photography": "Electronics > Photography",
    "tv": "Electronics > Televisions",
    "television": "Electronics > Televisions",
    "tvs": "Electronics > Televisions",
    "gaming": "Electronics > Gaming",
    "video games": "Electronics > Gaming",
    "console": "Electronics > Gaming",
    "consoles": "Electronics > Gaming",
    "wearables": "Electronics > Wearables",
    "smartwatch": "Electronics > Wearables",
    "accessories": "Electronics > Accessories",
    "computer accessories": "Electronics > Accessories",
    # books & media
    "books": "Books",
    "book": "Books",
    "literature": "Books",
    "novels": "Books",
    "fiction": "Books > Fiction",
    "non-fiction": "Books > Non-Fiction",
    "nonfiction": "Books > Non-Fiction",
    "childrens books": "Books > Children's",
    "textbooks": "Books > Textbooks",
    "academic": "Books > Academic",
    "music": "Media > Music",
    "dvds": "Media > DVD & Blu-ray",
    "dvd": "Media > DVD & Blu-ray",
    "blu-ray": "Media > DVD & Blu-ray",
    "movies": "Media > Movies",
    # fashion
    "fashion": "Apparel",
    "clothing": "Apparel",
    "clothes": "Apparel",
    "apparel": "Apparel",
    "mens clothing": "Apparel > Men",
    "mens": "Apparel > Men",
    "womens clothing": "Apparel > Women",
    "womens": "Apparel > Women",
    "kids clothing": "Apparel > Kids",
    "shoes": "Apparel > Footwear",
    "footwear": "Apparel > Footwear",
    "jewellery": "Accessories > Jewellery",
    "jewelry": "Accessories > Jewellery",
    "watches": "Accessories > Watches",
    "bags": "Accessories > Bags",
    "handbags": "Accessories > Bags",
    # home & living
    "home": "Home & Living",
    "home & living": "Home & Living",
    "household": "Home & Living",
    "kitchen": "Home & Living > Kitchen",
    "kitchenware": "Home & Living > Kitchen",
    "furniture": "Home & Living > Furniture",
    "decor": "Home & Living > Home Decor",
    "home decor": "Home & Living > Home Decor",
    "bedding": "Home & Living > Bedding",
    "bath": "Home & Living > Bath",
    "garden": "Home & Living > Garden",
    "toys": "Toys & Games",
    "toys & games": "Toys & Games",
    "games": "Toys & Games",
    "baby": "Baby & Kids",
    "baby & kids": "Baby & Kids",
    "kids": "Baby & Kids",
    # grocery & health
    "grocery": "Grocery",
    "groceries": "Grocery",
    "food": "Grocery > Food",
    "beverages": "Grocery > Beverages",
    "drinks": "Grocery > Beverages",
    "snacks": "Grocery > Snacks",
    "beauty": "Beauty & Personal Care",
    "personal care": "Beauty & Personal Care",
    "health": "Health",
    "health & care": "Health",
    "sports": "Sports & Outdoors",
    "sports & outdoors": "Sports & Outdoors",
    "fitness": "Sports & Outdoors > Fitness",
    "outdoor": "Sports & Outdoors",
    "camping": "Sports & Outdoors > Camping",
    "automotive": "Automotive",
    "car": "Automotive",
    "office": "Office & Stationery",
    "stationery": "Office & Stationery",
    "pet supplies": "Pets",
    "pets": "Pets",
    "toys & games > puzzles": "Toys & Games > Puzzles",
    "books > textbooks": "Books > Textbooks",
    "uncategorised": "Uncategorised",
    "uncategorized": "Uncategorised",
    "unknown": "Uncategorised",
    "misc": "Uncategorised",
    "other": "Uncategorised",
    "default": "Uncategorised",
}

_UNAVAILABLE_TOKENS = (
    "free",
    "n/a",
    "na",
    "none",
    "null",
    "unavailable",
    "-",
    "--",
    "call for price",
    "poa",
    "tbd",
    "?",
    "",
)
_IN_STOCK_TOKENS = (
    "in stock",
    "instock",
    "available",
    "yes",
    "true",
    "add to cart",
    "add to basket",
    "order now",
    "buy now",
    "ships",
    "in_stock",
    "instock!",
    "stocked",
    "on stock",
)
_OUT_OF_STOCK_TOKENS = (
    "out of stock",
    "outofstock",
    "unavailable",
    "sold out",
    "no stock",
    "backordered",
    "discontinued",
    "currently unavailable",
    "temporarily out of stock",
)
_PREORDER_TOKENS = ("preorder", "pre-order", "pre order", "backorder", "coming soon", "notify me")
_LIMITED_TOKENS = ("low stock", "only", "limited", "few left", "last chance", "hurry")


@dataclass(frozen=True)
class PriceInfo:
    """Result of parsing a price string."""

    amount: float | None
    currency: str | None
    raw: str | None
    confidence: float = 0.0
    is_range: bool = False
    range_low: float | None = None
    range_high: float | None = None
    matched_pattern: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.amount is not None and self.amount >= 0


@dataclass(frozen=True)
class RatingInfo:
    """Result of parsing a rating string."""

    value: float | None  # normalised to a 0-5 scale
    raw_value: float | None
    scale: float
    count: int | None
    raw: str | None


# --------------------------------------------------------------------------------------
# Text cleaning
# --------------------------------------------------------------------------------------
def strip_html(value: str | None) -> str:
    """Remove HTML markup and unescape entities."""
    if not value:
        return ""
    import html

    text = _HTML_TAG_RE.sub(" ", value)
    return _WHITESPACE_RE.sub(" ", html.unescape(text)).strip()


def normalise_unicode(value: str | None) -> str:
    """NFKC fold + smart punctuation + control character removal."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).translate(_CHAR_MAP)
    return _CONTROL_RE.sub("", text)


def collapse_whitespace(value: str | None) -> str:
    return _WHITESPACE_RE.sub(" ", (value or "")).strip()


def clean_product_name(name: str | None, *, max_length: int = 400) -> str:
    """Produce a clean, human-friendly product title.

    Steps: strip HTML -> unicode fold -> drop promo prefixes/suffixes -> remove
    bracketed marketing tags -> collapse punctuation/whitespace -> title-case words
    that are entirely lower-case (keeps intentional casing such as "iPhone").
    """
    if not name:
        return ""
    text = strip_html(normalise_unicode(name))
    if not text:
        return ""
    text = _PROMO_PREFIX_RE.sub("", text)
    text = _WEAK_PREFIX_ALLCAPS_RE.sub("", text) if text.split(" ")[0].isupper() else text
    text = _WEAK_PREFIX_PUNCT_RE.sub("", text)
    text = _PROMO_SUFFIX_RE.sub("", text)
    text = _BRACKETED_RE.sub(" ", text)
    text = re.sub(r"[\u2022\u00b7|]+", " - ", text)
    text = _MULTI_PUNCT_RE.sub(" ", text)
    text = collapse_whitespace(text.strip(" -_"))
    if not text:
        return ""
    if text.islower():
        text = _smart_title(text)
    if len(text) > max_length:
        text = text[:max_length].rsplit(" ", 1)[0]
    return text


def _smart_title(text: str) -> str:
    """Title-case while keeping small words lowercase and preserving known acronyms."""
    minor = {"and", "or", "of", "the", "for", "with", "in", "on", "to", "a", "an", "at", "by", "vs"}
    preserve = {
        "usb",
        "hd",
        "4k",
        "8k",
        "3d",
        "2d",
        "wifi",
        "usb-c",
        "tv",
        "led",
        "lcd",
        "oled",
        "nfc",
        "gps",
        "dlna",
        "ac",
        "dc",
    }
    words = text.split(" ")
    out: list[str] = []
    for index, word in enumerate(words):
        stripped = word.strip("()[]{}/")
        if stripped.lower() in preserve:
            out.append(word.upper() if len(stripped) <= 3 else word.upper())
        elif index not in (0, len(words) - 1) and word.lower() in minor:
            out.append(word.lower())
        else:
            out.append(word[:1].upper() + word[1:] if word else word)
    return " ".join(out)


def normalise_name_key(name: str | None) -> str:
    """Aggressive comparison key: lowercase alphanumerics with stopwords removed."""
    if not name:
        return ""
    text = normalise_unicode(name).lower()
    text = _PROMO_PREFIX_RE.sub("", text)
    text = _WEAK_PREFIX_ALLCAPS_RE.sub("", text) if text.split(" ")[0].isupper() else text
    text = _WEAK_PREFIX_PUNCT_RE.sub("", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = [t for t in _WORD_RE.findall(text) if t not in STOPWORDS]
    if not tokens:  # keep at least one token for names made entirely of stopwords
        tokens = _WORD_RE.findall(text)
    return " ".join(sorted(set(tokens)))


def name_fingerprint(name: str | None, brand: str | None = None) -> str:
    """Stable hash used for exact-match blocking."""
    key = normalise_name_key(name)
    brand_key = normalise_name_key(brand) if brand else ""
    return hashlib.sha1(f"{brand_key}|{key}".encode()).hexdigest()[:32]


def blocking_key(name: str | None, length: int | None = None) -> str:
    """Cheap blocking key so fuzzy comparisons only run on plausible candidates."""
    length = length or 4
    key = normalise_name_key(name)
    return key[:length] if key else ""


def clean_brand(brand: str | None) -> str | None:
    if not brand:
        return None
    value = strip_html(normalise_unicode(brand))
    value = re.sub(r"^(by|brand[:\s]+)", "", value, flags=re.IGNORECASE)
    value = collapse_whitespace(value.strip(" -_,|"))
    if not value or value.lower() in STOPWORDS:
        return None
    return value[:128]


def truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    value = str(value)
    return value if len(value) <= limit else value[: limit - 1] + "\u2026"


# --------------------------------------------------------------------------------------
# Category normalisation
# --------------------------------------------------------------------------------------
def normalise_category(category: str | None, *, default: str = "Uncategorised") -> str:
    """Canonicalise a category string, preserving a ``Parent > Child`` hierarchy."""
    if not category:
        return default
    raw = strip_html(normalise_unicode(category))
    raw = raw.replace("\\", "/").replace("|", ">").replace("»", ">").replace("›", ">")
    raw = raw.replace("->", ">").replace("=>", ">")
    raw = re.sub(r"\s+/\s+", " > ", raw)  # "Books / Textbooks" -> hierarchy
    if raw.count("/") <= 3:  # breadcrumb style: "electronics/mobile phones"
        raw = raw.replace("/", " > ")
    parts = [collapse_whitespace(p).strip(" >-/") for p in raw.split(">")]
    parts = [p for p in parts if p]
    if not parts:
        return default
    canonical: list[str] = []
    for part in parts:
        key = part.lower().strip()
        mapped = CATEGORY_SYNONYMS.get(key)
        if mapped is None:
            mapped = "Uncategorised" if key in {"unknown", "n/a", "na", "none"} else _titleise_category(part)
        for piece in mapped.split(">"):
            piece = piece.strip()
            if piece and piece not in canonical:
                canonical.append(piece)
    return " > ".join(canonical) if canonical else default


def _titleise_category(value: str) -> str:
    keep_lower = {"and", "of", "the", "for", "with", "&", "to"}
    words = []
    for word in value.split(" "):
        words.append(word.lower() if word.lower() in keep_lower else _smart_title(word))
    return " ".join(w for w in words if w)


def category_slug(category: str | None) -> str:
    """URL-safe slug for a (possibly hierarchical) category path."""
    base = normalise_category(category).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return slug[:180] or "uncategorised"


def category_levels(category: str | None) -> int:
    return len(normalise_category(category).split(">"))


# --------------------------------------------------------------------------------------
# Price / currency normalisation
# --------------------------------------------------------------------------------------
_NUM = r"\d{1,3}(?:[.,\s\u00a0]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_PRICE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "symbol_prefix",
        re.compile(rf"(?P<cur>[$€£¥₹₩₺₽₪₫₱₦]|US\$|R\$|A\$|C\$|zł|C)\s*(?P<amt>{_NUM})", re.IGNORECASE),
    ),
    (
        "symbol_suffix",
        re.compile(
            rf"(?P<amt>{_NUM})\s*(?P<cur>[$€£¥₹₩₺₽₪₫₱₦]|kr|zł|USD|EUR|GBP|JPY|INR|AUD|CAD|CHF|SEK|PLN|TRY|BRL|RUB)?"
        ),
    ),
    (
        "code_prefix",
        re.compile(
            rf"(?P<cur>USD|EUR|GBP|JPY|CNY|INR|AUD|CAD|CHF|SEK|PLN|TRY|BRL|RUB|ZAR|MXN|SGD|HKD|KRW|AED|SAR|EGP|ILS|PHP|NGN)\s*[:\s]?\s*(?P<amt>{_NUM})",
            re.IGNORECASE,
        ),
    ),
    (
        "code_suffix",
        re.compile(
            rf"(?P<amt>{_NUM})\s*(?P<cur>USD|EUR|GBP|JPY|CNY|INR|AUD|CAD|CHF|SEK|PLN|TRY|BRL|RUB|ZAR|MXN|SGD|HKD|KRW|AED|SAR|EGP|ILS|PHP|NGN)\b",
            re.IGNORECASE,
        ),
    ),
    ("bare", re.compile(rf"(?<![0-9])(?P<amt>{_NUM})(?![0-9])")),
)

#: Confidence per pattern - higher means stronger evidence of a real price.
_PATTERN_CONFIDENCE: dict[str, float] = {
    "code_prefix": 0.95,
    "symbol_prefix": 0.95,
    "code_suffix": 0.92,
    "symbol_suffix": 0.88,
    "bare": 0.60,
}

_UNAVAILABLE_RE = re.compile(
    r"^\s*(?:free|n/?a|null|none|unavailable|--|-|—|poa|call for price|tbd|ask for price)\s*$",
    re.IGNORECASE,
)


def parse_number(text: str | None) -> float | None:
    """Parse a numeric string handling ``1,234.56`` / ``1.234,56`` / ``1 234,56``."""
    if text is None:
        return None
    value = normalise_unicode(str(text)).strip()
    if not value:
        return None
    if not re.search(r"\d", value):
        return None
    value = value.replace("\u00a0", "").replace(" ", "").replace("'", "")
    has_comma, has_dot = "," in value, "." in value
    if has_comma and has_dot:
        # The right-most separator is the decimal separator.
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif has_comma:
        # "1,499" -> thousands, "45,90" -> decimal. A single separator followed by
        # exactly three digits is the classic thousands grouping.
        decimals = value.split(",")[-1]
        value = (
            value.replace(",", "")
            if (len(decimals) == 3 and value.count(",") == 1)
            else value.replace(",", ".")
        )
    elif has_dot:
        # A dot with exactly three trailing digits is ambiguous; we keep it as a
        # decimal point (US/en-GB default) unless several dots are used as grouping.
        decimals = value.split(".")[-1]
        if len(decimals) == 3 and value.count(".") > 1:
            value = value.replace(".", "")
    try:
        return float(value)
    except ValueError:
        return None


def normalise_currency(
    value: str | None, *, default: str | None = None, hint: str | None = None
) -> str | None:
    """Resolve a currency code from a code, symbol or ambiguous ``$``.

    When ``value`` is a longer string (e.g. ``"Was $49.99 Now $39.99"``) the most
    frequently occurring known symbol is used.
    """
    if not value:
        return default or hint
    text = normalise_unicode(value).strip()
    if not text:
        return default or hint
    upper = text.upper()
    if upper in STATIC_FX_RATES:
        return upper
    lowered = text.lower().strip(" .,()")
    if lowered in CURRENCY_SYMBOLS:
        return CURRENCY_SYMBOLS[lowered]
    compact = lowered.replace(" ", "")
    if compact in CURRENCY_SYMBOLS:
        return CURRENCY_SYMBOLS[compact]
    for token, code in CURRENCY_SYMBOLS.items():
        if len(token) >= 3 and token in compact:
            return code
    # Fall back to the dominant currency symbol found inside a longer text blob.
    counts: dict[str, int] = {}
    for token, code in CURRENCY_SYMBOLS.items():
        if token.isalpha() and len(token) < 3:
            continue
        occurrences = text.count(token)
        if occurrences:
            counts[code] = counts.get(code, 0) + occurrences
    if counts:
        return max(counts.items(), key=lambda item: item[1])[0]
    return default or hint


def detect_currency_locale(text: str | None, url: str | None = None, html: str | None = None) -> str | None:
    """Heuristically resolve the page/feed currency from text, URL or markup."""
    if url:
        host = re.sub(r"^www\.", "", url.lower())
        mapping = {
            ".co.uk": "GBP",
            ".uk/": "GBP",
            "amazon.co.uk": "GBP",
            "ebay.co.uk": "GBP",
            ".de": "EUR",
            ".fr": "EUR",
            ".it": "EUR",
            ".es": "EUR",
            ".nl": "EUR",
            ".eu": "EUR",
            ".ca": "CAD",
            ".com.au": "AUD",
            ".co.nz": "AUD",
            ".co.jp": "JPY",
            ".jp": "JPY",
            ".in": "INR",
            ".cn": "CNY",
            ".com.br": "BRL",
            ".com.mx": "MXN",
            ".ae": "AED",
            ".sa": "SAR",
            ".eg": "EGP",
            ".se": "SEK",
            ".ch": "CHF",
            ".pl": "PLN",
            ".za": "ZAR",
            ".sg": "SGD",
            ".hk": "HKD",
            ".kr": "KRW",
            ".tr": "TRY",
            ".il": "ILS",
        }
        for needle, code in mapping.items():
            if needle in host:
                return code
    haystack = " ".join(filter(None, [text or "", (html or "")[:4000]]))
    counts: dict[str, int] = {}
    for token, code in CURRENCY_SYMBOLS.items():
        if len(token) <= 2:
            continue
        counts[code] = haystack.count(token)
    for currency_hint in ('itemprop="priceCurrency" content="', "priceCurrency", 'currency":"'):
        if currency_hint in haystack:
            match = re.search(r"(?:content=\"|\":\")([A-Z]{3})", haystack)
            if match and match.group(1) in STATIC_FX_RATES:
                return match.group(1)
    if counts:
        best = max(counts.items(), key=lambda item: item[1])
        return best[0] if best[1] > 0 else None
    return None


def parse_price(
    price_text: str | None,
    *,
    default_currency: str | None = None,
    locale_hint: str | None = None,
    max_value: float = 10_000_000.0,
) -> PriceInfo:
    """Extract a numeric price + currency from messy text.

    Handles symbol prefixes/suffixes, ISO codes, thousands separators with either
    ``.`` or ``,`` as decimal mark, ranges (``$10 - $20``), and non-numeric markers
    such as ``Free`` / ``N/A`` / ``Call for price``.
    """
    if price_text is None:
        return PriceInfo(None, None, None, 0.0)
    raw = normalise_unicode(str(price_text)).strip()
    if not raw or _UNAVAILABLE_RE.match(raw):
        return PriceInfo(None, normalise_currency(None, default=default_currency), raw, 0.0)

    # Ranges: take the midpoint for the headline price and keep both bounds.
    range_match = re.search(
        rf"(?P<low>{_NUM})\s*(?:-|–|—|to|until)\s*[$€£¥₹₺]?\s*(?P<high>{_NUM})",
        raw,
        re.IGNORECASE,
    )
    if range_match and not re.search(r"\b(was|now|mrp|rrp|list price)\b", raw, re.IGNORECASE):
        low, high = parse_number(range_match.group("low")), parse_number(range_match.group("high"))
        if low is not None and high is not None and low <= high:
            currency = normalise_currency(raw, default=locale_hint or default_currency)
            return PriceInfo(
                amount=round((low + high) / 2, 4),
                currency=currency,
                raw=raw,
                confidence=0.7,
                is_range=True,
                range_low=low,
                range_high=high,
                matched_pattern="range",
            )

    stripped = raw
    if re.search(r"\b(was|list price|mrp|rrp)\b", stripped, re.IGNORECASE):
        # "Was $49.99 Now $39.99" -> keep the current price only.
        now_match = re.search(rf"\bnow\b[^0-9$€£]*[$€£]?\s*(?P<amt>{_NUM})", stripped, re.IGNORECASE)
        if now_match:
            amount = parse_number(now_match.group("amt"))
            if amount is not None:
                return PriceInfo(
                    amount,
                    normalise_currency(stripped, default=locale_hint or default_currency),
                    raw,
                    0.85,
                    matched_pattern="was_now",
                )

    # Collect every candidate across all patterns, then keep the most trustworthy one.
    # Priority reflects how explicit the evidence is: an ISO code or a currency symbol
    # glued to the number beats a bare number.
    best: PriceInfo | None = None
    best_rank: tuple[float, int] = (-1.0, 0)
    for priority, (name, pattern) in enumerate(_PRICE_PATTERNS):
        for match in pattern.finditer(stripped):
            amount = parse_number(match.group("amt"))
            if amount is None or amount < 0 or amount > max_value:
                continue
            currency = normalise_currency(
                match.groupdict().get("cur"), default=locale_hint or default_currency
            )
            # A pattern whose optional currency group did not participate is only
            # weak evidence (e.g. a bare "12" matched by the symbol-suffix rule).
            confidence = (
                _PATTERN_CONFIDENCE[name]
                if match.groupdict().get("cur")
                else min(_PATTERN_CONFIDENCE[name], _PATTERN_CONFIDENCE["bare"])
            )
            candidate = PriceInfo(amount, currency, raw, confidence, matched_pattern=name)
            rank = (confidence, -priority)
            if best is None or rank > best_rank:
                best, best_rank = candidate, rank
    if best is None:
        return PriceInfo(None, normalise_currency(None, default=locale_hint or default_currency), raw, 0.0)
    if best.currency is None:
        best = PriceInfo(
            best.amount,
            locale_hint or default_currency,
            best.raw,
            best.confidence * 0.9,
            best.is_range,
            best.range_low,
            best.range_high,
            best.matched_pattern,
        )
    return best


def convert_to_usd(amount: float | None, currency: str | None) -> tuple[float | None, float]:
    """Convert to USD using the offline reference table."""
    if amount is None:
        return None, 1.0
    code = (currency or "USD").upper()
    rate = STATIC_FX_RATES.get(code)
    if rate is None:
        return amount, 1.0
    return round(amount * rate, 4), rate


def format_price(amount: float | None, currency: str | None = "USD") -> str:
    """Human-friendly price rendering used by the dashboard and CLI reports."""
    if amount is None:
        return "\u2014"
    code = (currency or "USD").upper()
    symbol = CURRENCY_SYMBOL_OUT.get(code, f"{code} ")
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return "-"
    if abs(value) >= 1000:
        return f"{symbol}{value:,.0f}"
    if value == int(value):
        return f"{symbol}{value:,.0f}"
    return f"{symbol}{value:,.2f}"


def percent_change(old: float | None, new: float | None) -> float | None:
    """Percentage change from ``old`` to ``new`` (None-safe, symmetric guard)."""
    if old is None or new is None:
        return None
    try:
        old_f, new_f = float(old), float(new)
    except (TypeError, ValueError):
        return None
    if old_f == 0:
        return None if new_f == 0 else 100.0
    return round(((new_f - old_f) / abs(old_f)) * 100, 4)


# --------------------------------------------------------------------------------------
# Rating / availability
# --------------------------------------------------------------------------------------
_RATING_RE = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?:/|out of|\s+of\s+)\s*(?P<scale>\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
_RATING_BARE_RE = re.compile(r"(?<![\d.])(?P<value>\d+(?:[.,]\d+)?)(?![\d.])")
_RATING_COUNT_RE = re.compile(r"([\d,.]+)\s*(?:ratings?|reviews?|votes?|customers?)\b", re.IGNORECASE)
_STAR_RE = re.compile(r"([\d.,]+)\s*(?:out of 5|out of five|\u2605|\*)", re.IGNORECASE)


def parse_rating(
    rating_text: str | None,
    *,
    count_text: str | None = None,
    star_elements: int | None = None,
    target_scale: float = 5.0,
) -> RatingInfo:
    """Parse and rescale a rating to a 0-``target_scale`` basis."""
    raw = normalise_unicode(rating_text or "").strip()
    if not raw and star_elements is None:
        raw = normalise_unicode(count_text or "").strip()
    if not raw:
        return RatingInfo(None, None, target_scale, None, rating_text)

    value: float | None = None
    scale: float = target_scale

    match = _RATING_RE.search(raw)
    if match:
        value = parse_number(match.group("value"))
        scale = parse_number(match.group("scale")) or target_scale
    else:
        star_match = _STAR_RE.search(raw)
        if star_match:
            value = parse_number(star_match.group(1))
            scale = target_scale
        else:
            percent = re.search(r"(\d+(?:[.,]\d+)?)\s*%", raw)
            if percent and re.search(r"\b(?:percent|percentage)\b", raw, re.IGNORECASE):
                value = (parse_number(percent.group(1)) or 0) / 20.0
                scale = target_scale
            elif star_elements is not None and 0 <= star_elements <= 5:
                value = float(star_elements)
            else:
                bare = _RATING_BARE_RE.search(raw)
                if bare:
                    candidate = parse_number(bare.group("value"))
                    if candidate is not None and 0 <= candidate <= target_scale:
                        value = candidate
                    elif candidate is not None and 0 <= candidate <= 100:
                        value = candidate / (100 / target_scale)
                        scale = target_scale
    if value is None:
        return RatingInfo(None, None, target_scale, None, rating_text)

    value = max(0.0, min(value, scale))
    scaled = round(value * target_scale / scale, 3) if scale else value
    count = None
    count_source = f"{raw} {count_text or ''}"
    count_match = _RATING_COUNT_RE.search(count_source)
    if count_match:
        parsed_count = parse_number(count_match.group(1))
        count = int(parsed_count) if parsed_count is not None else None
    return RatingInfo(value=scaled, raw_value=value, scale=scale, count=count, raw=rating_text)


def normalise_availability(value: str | None, *, in_stock_flag: bool | None = None) -> tuple[str, bool]:
    """Return ``(status, in_stock)`` from free-form availability text."""
    if in_stock_flag is not None:
        return ("in_stock", True) if in_stock_flag else ("out_of_stock", False)
    if value is None:
        return "unknown", False
    text = collapse_whitespace(normalise_unicode(str(value)).lower())
    if not text:
        return "unknown", False
    for token in _OUT_OF_STOCK_TOKENS:
        if token in text:
            return "out_of_stock", False
    for token in _PREORDER_TOKENS:
        if token in text:
            return "preorder", False
    for token in _IN_STOCK_TOKENS:
        if token in text:
            return "in_stock", True
    for token in _LIMITED_TOKENS:
        if token in text:
            return "limited_stock", True
    if text in {"true", "yes", "1", "y"}:
        return "in_stock", True
    if text in {"false", "no", "0", "n"}:
        return "out_of_stock", False
    return "unknown", False


def availability_slug(value: str | None) -> str:
    status, _ = normalise_availability(value)
    return status


# --------------------------------------------------------------------------------------
# Validation helpers used by the data-quality framework
# --------------------------------------------------------------------------------------
def is_valid_price(value: float | None, *, min_price: float = 0.0, max_price: float = 1_000_000.0) -> bool:
    if value is None:
        return False
    try:
        value = float(value)
    except (TypeError, ValueError):
        return False
    return min_price <= value <= max_price


def is_valid_rating(value: float | None, *, min_rating: float = 0.0, max_rating: float = 5.0) -> bool:
    if value is None:
        return False
    try:
        value = float(value)
    except (TypeError, ValueError):
        return False
    return min_rating <= value <= max_rating


def validate_url(url: str | None) -> bool:
    if not url:
        return False
    return bool(re.match(r"^https?://[^\s/?#]+", str(url).strip(), re.IGNORECASE))


def content_hash(*parts: object) -> str:
    """Deterministic content hash used for staging-zone de-duplication."""
    joined = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


__all__ = [
    "PriceInfo",
    "RatingInfo",
    "CATEGORY_SYNONYMS",
    "CURRENCY_SYMBOLS",
    "STATIC_FX_RATES",
    "strip_html",
    "normalise_unicode",
    "collapse_whitespace",
    "clean_product_name",
    "normalise_name_key",
    "name_fingerprint",
    "blocking_key",
    "clean_brand",
    "truncate",
    "normalise_category",
    "category_slug",
    "category_levels",
    "parse_number",
    "parse_price",
    "normalise_currency",
    "detect_currency_locale",
    "convert_to_usd",
    "format_price",
    "percent_change",
    "parse_rating",
    "normalise_availability",
    "availability_slug",
    "is_valid_price",
    "is_valid_rating",
    "validate_url",
    "content_hash",
]
