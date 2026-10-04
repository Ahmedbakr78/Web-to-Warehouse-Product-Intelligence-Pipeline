"""Duplicate detection and fuzzy entity resolution.

No third-party fuzzy-matching library is required: the module implements the classic
similarity measures (Levenshtein, Jaro-Winkler, token-set ratio and trigram Dice
coefficient) so the algorithm is transparent, fast and dependency free.

Matching strategy (cheapest first, so large catalogues stay fast):

1. **Exact fingerprint** - SHA-1 of the normalised name + brand.
2. **Blocking** - only candidates that share a blocking prefix are compared, which
   keeps the comparison set to a handful of rows instead of the whole table.
3. **Similarity scoring** - a weighted blend of the four measures plus a brand bonus.
4. **Auto-merge** - above the threshold the observation is folded into the surviving
   product (highest observation count wins) and the merge is logged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Iterable, Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.ingestion.cleaning import (
    STOPWORDS,
    blocking_key,
    clean_brand,
    name_fingerprint,
    normalise_name_key,
    normalise_unicode,
)
from app.models.dimensions import DimProduct

log = get_logger(__name__)

TRIGRAM_CACHE_SIZE = 50_000


# --------------------------------------------------------------------------------------
# Similarity primitives
# --------------------------------------------------------------------------------------
def levenshtein(a: str, b: str, *, max_distance: int | None = None) -> int:
    """Classic edit distance with two-row DP and early abandonment."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if max_distance is not None and abs(len(a) - len(b)) > max_distance:
        return max_distance + 1

    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        best = current[0]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            value = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            current.append(value)
            best = min(best, value)
        previous = current
        if max_distance is not None and best > max_distance:
            return max_distance + 1
    return previous[-1]


def levenshtein_ratio(a: str, b: str) -> float:
    longest = max(len(a), len(b))
    return 1.0 if longest == 0 else 1.0 - levenshtein(a, b) / longest


def jaro(a: str, b: str) -> float:
    """Jaro similarity (robust to transpositions and single-character typos)."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    match_distance = max(len(a), len(b)) // 2 - 1
    if match_distance < 0:
        match_distance = 0
    a_flags = [False] * len(a)
    b_flags = [False] * len(b)
    matches = 0
    for i, ch in enumerate(a):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len(b))
        for j in range(start, end):
            if not b_flags[j] and b[j] == ch:
                a_flags[i] = b_flags[j] = True
                matches += 1
                break
    if matches == 0:
        return 0.0
    transpositions = 0
    k = 0
    for i, flag in enumerate(a_flags):
        if not flag:
            continue
        while not b_flags[k]:
            k += 1
        if a[i] != b[k]:
            transpositions += 1
        k += 1
    transpositions //= 2
    return (matches / len(a) + matches / len(b) + (matches - transpositions) / matches) / 3


def jaro_winkler(a: str, b: str, *, prefix_scale: float = 0.1, max_prefix: int = 4) -> float:
    """Jaro-Winkler similarity - favours products that share a common prefix."""
    base = jaro(a, b)
    if base < 0.7:
        return base
    prefix = 0
    for x, y in zip(a[:max_prefix], b[:max_prefix]):
        if x != y:
            break
        prefix += 1
    return base + prefix * prefix_scale * (1 - base)


def _tokens(value: str) -> list[str]:
    return [token for token in value.split() if token and token not in STOPWORDS]


def token_sort_ratio(a: str, b: str) -> float:
    """Order-insensitive comparison of two whitespace token sequences."""
    ta, tb = sorted(a.split()), sorted(b.split())
    return levenshtein_ratio(" ".join(ta), " ".join(tb))


def token_set_ratio(a: str, b: str) -> float:
    """Best of three token-set comparisons (mirrors fuzzywuzzy's algorithm)."""
    ta, tb = set(_tokens(a)), set(_tokens(b))
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    intersection = ta & tb
    left_diff = " ".join(sorted(ta - tb))
    right_diff = " ".join(sorted(tb - ta))
    left_join = " ".join(sorted(ta))
    right_join = " ".join(sorted(tb))
    candidates = (
        levenshtein_ratio(left_join, right_join),
        levenshtein_ratio(left_join, " ".join(sorted(intersection)) + " " + left_diff),
        levenshtein_ratio(" ".join(sorted(intersection)) + " " + right_diff, right_join),
    )
    return max(candidates)


@lru_cache(maxsize=TRIGRAM_CACHE_SIZE)
def _trigrams(value: str) -> frozenset[str]:
    padded = f"  {value} "
    return frozenset(padded[i : i + 3] for i in range(len(padded) - 2))


def trigram_similarity(a: str, b: str) -> float:
    """Dice coefficient over character trigrams."""
    ta, tb = _trigrams(a), _trigrams(b)
    if not ta or not tb:
        return 0.0
    overlap = len(ta & tb)
    return (2 * overlap) / (len(ta) + len(tb))


_DIGIT_RUN_RE = re.compile(r"\d+")


def _squash(value: str) -> str:
    """Lower-case alphanumeric form with every separator removed."""
    return re.sub(r"[^a-z0-9]+", "", normalise_unicode(value).lower())


def digit_signature(value: str) -> tuple[str, ...]:
    """Ordered digit runs inside a name (model numbers, capacities, sizes).

    Two products whose digit signatures differ are treated as *different SKUs* even
    when the text is otherwise nearly identical ("Canon EOS R6" vs "Canon EOS R5",
    "Nike Pegasus 40" vs "Nike Pegasus 39").  This single rule removes the classic
    false-positive duplicate in product matching.
    """
    return tuple(_DIGIT_RUN_RE.findall(normalise_unicode(value).lower()))


def digit_signature_factor(sig_a: tuple[str, ...], sig_b: tuple[str, ...]) -> float:
    """Multiplier applied to the similarity score based on digit signatures."""
    if not sig_a or not sig_b:
        return 1.0
    if sig_a == sig_b:
        return 1.0
    differences = sum(1 for x, y in zip(sig_a, sig_b) if x != y) + abs(len(sig_a) - len(sig_b))
    if differences <= 1:
        return 0.85
    return 0.60


def combined_similarity(
    name_a: str,
    name_b: str,
    *,
    brand_a: str | None = None,
    brand_b: str | None = None,
    category_a: str | None = None,
    category_b: str | None = None,
) -> tuple[float, dict[str, float]]:
    """Blend the individual measures into a single 0-1 similarity score."""
    key_a = normalise_name_key(name_a)
    key_b = normalise_name_key(name_b)
    if not key_a or not key_b:
        return 0.0, {}

    if key_a == key_b:
        score = 1.0
        parts: dict[str, float] = {"exact_key": 1.0}
    else:
        # Character-level forms are insensitive to tokenisation differences
        # ("256GB" vs "256 GB"), which are extremely common in the wild.
        squash_a, squash_b = _squash(name_a), _squash(name_b)
        compact_a, compact_b = key_a.replace(" ", ""), key_b.replace(" ", "")
        compact = max(trigram_similarity(compact_a, compact_b), jaro_winkler(compact_a, compact_b))
        squash_sim = max(jaro_winkler(squash_a, squash_b), trigram_similarity(squash_a, squash_b))
        parts = {
            "token_set": round(token_set_ratio(key_a, key_b), 4),
            "jaro_winkler": round(jaro_winkler(key_a, key_b), 4),
            "trigram": round(trigram_similarity(key_a, key_b), 4),
            "levenshtein": round(levenshtein_ratio(key_a, key_b), 4),
            "compact": round(compact, 4),
            "squash": round(squash_sim, 4),
        }
        blend = (
            0.20 * parts["token_set"]
            + 0.15 * parts["jaro_winkler"]
            + 0.10 * parts["trigram"]
            + 0.05 * parts["levenshtein"]
            + 0.20 * parts["compact"]
            + 0.30 * parts["squash"]
        )
        # Character-level evidence on its own is strong enough evidence of an exact
        # re-listing (only punctuation/tokenisation differs), so it is allowed to
        # short-circuit the weighted blend - with a small safety discount.
        character_evidence = max(squash_sim, compact) * 0.97
        parts["blend"] = round(blend, 4)
        score = max(blend, character_evidence)

    factor = digit_signature_factor(digit_signature(name_a or ""), digit_signature(name_b or ""))
    parts["digit_factor"] = factor
    score *= factor

    brand_a_norm = (clean_brand(brand_a) or "").lower()
    brand_b_norm = (clean_brand(brand_b) or "").lower()
    if brand_a_norm and brand_b_norm:
        brand_score = 1.0 if brand_a_norm == brand_b_norm else trigram_similarity(brand_a_norm, brand_b_norm)
        parts["brand"] = round(brand_score, 4)
        score = score * 0.88 + brand_score * 0.12
    elif not brand_a_norm and not brand_b_norm:
        parts["brand"] = 1.0

    if category_a and category_b:
        cat_a, cat_b = category_a.lower(), category_b.lower()
        cat_score = 1.0 if cat_a == cat_b else (0.7 if cat_a in cat_b or cat_b in cat_a else 0.0)
        parts["category"] = cat_score
        score = min(1.0, score + 0.03 * cat_score)

    return round(min(score, 1.0), 4), parts


# --------------------------------------------------------------------------------------
# Duplicate resolution engine
# --------------------------------------------------------------------------------------
@dataclass
class MatchResult:
    """Outcome of a duplicate search for one candidate product."""

    product_id: int | None
    strategy: str                     # exact | fingerprint | blocked_exact | fuzzy | new
    score: float
    fingerprint: str
    blocking_key: str
    parts: dict[str, float] = field(default_factory=dict)
    candidate_id: int | None = None

    @property
    def is_duplicate(self) -> bool:
        return self.product_id is not None


@dataclass
class DedupeStats:
    examined: int = 0
    exact: int = 0
    fuzzy: int = 0
    merged: int = 0
    created: int = 0
    blocked_comparisons: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "examined": self.examined,
            "exact_matches": self.exact,
            "fuzzy_matches": self.fuzzy,
            "merged": self.merged,
            "new_products": self.created,
            "blocked_comparisons": self.blocked_comparisons,
        }


class DedupeEngine:
    """Stateful, database-backed duplicate detector."""

    def __init__(
        self,
        session: Session,
        *,
        threshold: float | None = None,
        blocking_length: int | None = None,
        candidate_limit: int | None = None,
    ) -> None:
        self.session = session
        self.threshold = threshold if threshold is not None else 0.90
        self.blocking_length = blocking_length or 4
        self.candidate_limit = candidate_limit or 25
        self.stats = DedupeStats()
        self._fingerprint_cache: dict[str, int] = {}

    # ------------------------------------------------------------------ queries
    def _load_fingerprints(self) -> dict[str, int]:
        if not self._fingerprint_cache:
            rows = self.session.execute(
                select(DimProduct.product_id, DimProduct.fingerprint)
            ).all()
            self._fingerprint_cache = {row[1]: row[0] for row in rows if row[1]}
        return self._fingerprint_cache

    def _blocking_candidates(self, block: str, brand: str | None) -> list[DimProduct]:
        """Rows whose normalised name starts with the same blocking prefix.

        ``normalized_name`` is the sorted-token comparison key, so a prefix match on
        it is index friendly and keeps the candidate set tiny even for 100k+ SKUs.
        """
        if not block:
            return []
        prefix = f"{block}%"
        limit = self.candidate_limit * 6
        rows: list[DimProduct] = []
        seen: set[int] = set()
        for column in (DimProduct.normalized_name, DimProduct.canonical_name):
            for row in self.session.execute(select(DimProduct).where(column.like(prefix)).limit(limit)).scalars():
                if row.product_id not in seen:
                    seen.add(row.product_id)
                    rows.append(row)
        self.stats.blocked_comparisons += len(rows)
        if brand:
            brand_key = (clean_brand(brand) or "").lower()
            branded = [row for row in rows if (row.brand or "").lower() == brand_key]
            if branded:
                return branded[: self.candidate_limit]
        return rows[: self.candidate_limit]

    # ------------------------------------------------------------------ matching
    def find_match(
        self,
        name: str,
        *,
        brand: str | None = None,
        category: str | None = None,
        exclude_product_id: int | None = None,
    ) -> MatchResult:
        """Find the best existing product for ``name`` (or report a new product)."""
        self.stats.examined += 1
        fingerprint = name_fingerprint(name, brand)
        block = blocking_key(name, self.blocking_length)

        known = self._load_fingerprints()
        if fingerprint in known:
            self.stats.exact += 1
            return MatchResult(known[fingerprint], "exact", 1.0, fingerprint, block, {"exact_key": 1.0}, known[fingerprint])

        key = normalise_name_key(name)
        stmt = select(DimProduct).where(DimProduct.normalized_name == key)
        exact_row = self.session.execute(stmt).scalars().first()
        if exact_row and exclude_product_id != exact_row.product_id:
            self.stats.exact += 1
            return MatchResult(
                exact_row.product_id, "blocked_exact", 1.0, fingerprint, block,
                {"exact_key": 1.0}, exact_row.product_id,
            )

        best: MatchResult | None = None
        for candidate in self._blocking_candidates(block, brand):
            if exclude_product_id and candidate.product_id == exclude_product_id:
                continue
            score, parts = combined_similarity(
                name,
                candidate.canonical_name,
                brand_a=brand,
                brand_b=candidate.brand,
                category_a=category,
                category_b=self._category_name(candidate.category_id),
            )
            if best is None or score > best.score:
                best = MatchResult(
                    candidate.product_id, "fuzzy", score, fingerprint, block, parts, candidate.product_id
                )

        if best and best.score >= self.threshold:
            self.stats.fuzzy += 1
            self._fingerprint_cache.setdefault(fingerprint, best.product_id)
            return best

        return MatchResult(None, "new", best.score if best else 0.0, fingerprint, block, best.parts if best else {})

    def _category_name(self, category_id: int | None) -> str | None:
        if not category_id:
            return None
        from app.models.dimensions import DimCategory

        row = self.session.get(DimCategory, category_id)
        return row.path or row.name if row else None

    # ------------------------------------------------------------------ merging
    def merge_into(
        self,
        product: DimProduct,
        other: DimProduct,
        *,
        keep_observations: bool = True,
    ) -> DimProduct:
        """Fold ``other`` into ``product`` and mark ``other`` inactive."""
        if product.product_id == other.product_id:
            return product

        survivor, absorbed = (product, other)
        if (other.observation_count or 0) > (product.observation_count or 0):
            survivor, absorbed = (other, product)

        merged_sources = list((survivor.extra or {}).get("merged_from", []))
        if absorbed.source_code:
            merged_sources.append({"source": absorbed.source_code, "id": absorbed.source_product_id})
        extra = dict(survivor.extra or {})
        extra["merged_from"] = merged_sources[-20:]
        survivor.extra = extra
        survivor.observation_count = (survivor.observation_count or 0) + (
            absorbed.observation_count or 0
        ) + (1 if keep_observations else 0)
        survivor.is_active = True

        absorbed.is_active = False
        absorbed.matched_product_id = survivor.product_id
        absorbed.match_strategy = "merged"
        absorbed.match_score = None
        self._fingerprint_cache[absorbed.fingerprint] = survivor.product_id
        self.stats.merged += 1
        log.debug(
            "merged duplicate absorbed=%s survivor=%s (%s)",
            absorbed.product_id, survivor.product_id, absorbed.canonical_name,
        )
        return survivor

    def resolve_batch(
        self,
        candidates: Sequence[dict[str, Any]],
        *,
        key: str = "name",
    ) -> list[MatchResult]:
        """Resolve many candidates, reusing the fingerprint cache for speed."""
        return [self.find_match(item.get(key), brand=item.get("brand"), category=item.get("category")) for item in candidates]

    def register(self, product: DimProduct) -> None:
        """Remember a freshly created product so later items match it in-memory."""
        self._fingerprint_cache[product.fingerprint] = product.product_id

    def duplicates_in_iterable(self, names: Iterable[str]) -> list[tuple[str, str, float]]:
        """Offline duplicate discovery within one batch (used by the demo seeder)."""
        entries = [(name, normalise_name_key(name), blocking_key(name, self.blocking_length)) for name in names]
        found: list[tuple[str, str, float]] = []
        seen: dict[str, tuple[str, str]] = {}
        for original, key, block in entries:
            if not key:
                continue
            if block in seen:
                previous_original, previous_key = seen[block]
                score, _ = combined_similarity(previous_original, original)
                if score >= self.threshold:
                    found.append((previous_original, original, score))
                    continue
            seen.setdefault(block, (original, key))
        return found


__all__ = [
    "levenshtein",
    "levenshtein_ratio",
    "jaro",
    "jaro_winkler",
    "token_sort_ratio",
    "token_set_ratio",
    "trigram_similarity",
    "combined_similarity",
    "MatchResult",
    "DedupeStats",
    "DedupeEngine",
]