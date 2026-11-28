# Ahmed Medhat — ETL & Cleaning Lead

| | |
|---|---|
| **Weight** | 14% |
| **GitHub** | [@AhmedMedhatFarouk](https://github.com/AhmedMedhatFarouk) |
| **Role** | ETL & Cleaning Lead |
| **Component** | 29-step cleaner + 4-signal fuzzy dedupe + ETL loader support |
| **Full project** | [`project/`](project/) — complete pipeline, runs standalone |

---

## 1. Executive summary

Ahmed Medhat owns the **quality heart of the pipeline**: the 29-step normalisation engine that turns
messy upstream records into warehouse-grade products, and the 4-signal fuzzy dedupe that guarantees one
physical product = one `dim_product` row even when ten different sources spell it ten different ways.

His layer sits at stages **3–5** of the 9-stage ETL: *transform* (clean, normalise, enrich, validate),
*resolve* (match or create the product dimension, merge duplicates) and *load* (snapshot upserts into the
fact tables, keyed `(product_id, run_id)` so every run is idempotent).

The design principle he enforces: **clean deterministically, match fuzzily, and never let a duplicate
reach the warehouse.**

```mermaid
flowchart LR
    IN["RawProduct from 34 sources<br/>(Abd alla)"] --> CLEAN["29-step cleaner<br/>cleaning.py"]
    CLEAN --> DEDUPE["4-signal fuzzy dedupe<br/>dedupe.py"]
    DEDUPE -->|match| MERGE["merge into existing dim_product"]
    DEDUPE -->|new| CREATE["create new dim_product"]
    MERGE --> LOADER["loader.py<br/>snapshot upserts + aggregates"]
    CREATE --> LOADER
    LOADER --> WH[("warehouse 👑 → Alaa")]
```

---

## 2. The 29-step cleaner — five phases

```mermaid
flowchart TD
    START["Raw product fields"] --> P1

    subgraph P1["Phase 1 · Text & identity"]
        T1["strip_html"] --> T2["normalise_unicode (NFKC)"] --> T3["collapse_whitespace"]
        T3 --> T4["clean_product_name<br/>ALL-CAPS promo noise removed · smart title case · max 400"]
        T4 --> T5["clean_brand · truncate"]
        T5 --> T6["normalise_name_key → name_fingerprint → blocking_key"]
    end

    P1 --> P2

    subgraph P2["Phase 2 · Currency & price"]
        C1["parse_number<br/>multi-format numeric parsing"] --> C2["detect_currency_locale<br/>text · URL · HTML hints"]
        C2 --> C3["normalise_currency<br/>18+ currency codes"]
        C3 --> C4["parse_price<br/>symbols · separators · ranges"]
        C4 --> C5["convert_to_usd<br/>offline FX table"]
        C5 --> C6["format_price · percent_change"]
    end

    P2 --> P3

    subgraph P3["Phase 3 · Category"]
        G1["normalise_category<br/>Uncategorised default"] --> G2["titleise"] --> G3["category_slug · category_levels"]
    end

    P3 --> P4

    subgraph P4["Phase 4 · Rating & availability"]
        R1["parse_rating<br/>0–5 scales · decimals · counts"] --> R2["normalise_availability<br/>vocabulary → status + in_stock bool"]
        R2 --> R3["availability_slug"]
    end

    P4 --> P5

    subgraph P5["Phase 5 · Validation helpers"]
        V1["is_valid_price"] --> V2["is_valid_rating"] --> V3["validate_url"] --> V4["content_hash"]
    end

    P5 --> OUT["NormalizedProduct<br/>ready for resolve"]
```

| Phase | Key functions | Guarantee |
|-------|---------------|-----------|
| Text & identity | `strip_html`, `normalise_unicode`, `collapse_whitespace`, `clean_product_name`, `clean_brand`, `normalise_name_key`, `name_fingerprint`, `blocking_key` | deterministic, stable keys for dedupe |
| Currency & price | `parse_number`, `detect_currency_locale`, `normalise_currency`, `parse_price`, `convert_to_usd`, `format_price`, `percent_change` | one comparable `price_usd` for every source |
| Category | `normalise_category`, `category_slug`, `category_levels` | consistent taxonomy + hierarchy depth |
| Rating & availability | `parse_rating`, `normalise_availability`, `availability_slug` | one vocabulary for all sources |
| Validation | `is_valid_price`, `is_valid_rating`, `validate_url`, `content_hash` | feeds the 12-rule DQ framework (Alaa) |

---

## 3. The 4-signal fuzzy dedupe

```mermaid
flowchart TD
    N["New cleaned product"] --> S1{"Signal 1 · Exact fingerprint<br/>SHA-1(normalised name + brand)<br/>already in dim_product?"}
    S1 -- "hit" --> M1["MERGE into existing product_id<br/>strategy: exact (confidence 1.0)"]
    S1 -- "miss" --> S2["Signal 2 · Blocking<br/>collect candidates sharing the<br/>name prefix (blocking_key, default 4 chars)"]

    S2 --> S2Q{"Candidate's exact fingerprint<br/>matches?"}
    S2Q -- "hit" --> M2["MERGE<br/>strategy: blocked_exact"]
    S2Q -- "miss" --> S3["Signal 3 · Fuzzy similarity<br/>combined_similarity over the block"]

    S3 --> S3Q{"score ≥ threshold?"}
    S3Q -- "yes" --> M3["MERGE<br/>strategy: fuzzy"]
    S3Q -- "no" --> M4["CREATE new dim_product<br/>strategy: new"]

    M1 --> STATS["DedupeStats<br/>merged / created / strategies"]
    M2 --> STATS
    M3 --> STATS
    M4 --> STATS
    STATS --> RUN[("etl_run.duplicates_merged")]
```

### Similarity metrics inside `combined_similarity`

| Metric | Function | Catches |
|--------|----------|---------|
| Levenshtein (+ratio) | `levenshtein`, `levenshtein_ratio` | typos, small edits |
| Jaro / Jaro-Winkler | `jaro`, `jaro_winkler` | transpositions, prefixes |
| Token sort ratio | `token_sort_ratio` | word-order changes |
| Token set ratio | `token_set_ratio` | extra/missing words |
| Trigram similarity | `trigram_similarity` | spelling variants |
| Digit signature | `digit_signature`, `digit_signature_factor` | model numbers, sizes ("A3", "500ml") |

The blocking step keeps this near-linear: only candidates sharing the prefix are ever compared, and the
fingerprint cache (`DimProduct.fingerprint` map) makes the common exact-match path a single dict lookup.

---

## 4. Loader — how resolved products land in the warehouse

```mermaid
sequenceDiagram
    autonumber
    participant ETL as pipeline (👑)
    participant L as loader.py
    participant DB as Warehouse

    ETL->>L: load run batch
    L->>DB: upsert dim_product (create or matched from dedupe)
    L->>DB: upsert dim_category / dim_source / dim_currency rows as needed
    L->>DB: insert fact_price_snapshot (product_id, run_id) — idempotent
    L->>DB: record lifecycle events / price changes via reconcile
    L->>DB: refresh agg_category_daily (category-day aggregates)
    L-->>ETL: LoadStats (created · updated · merged · rejected)
```

---

## 5. Files he delivered (inside `project/`)

| Path | Deliverable |
|------|-------------|
| `app/ingestion/cleaning.py` | full 29-step normalisation engine (5 phases above) |
| `app/ingestion/dedupe.py` | fingerprints, blocking, 6 similarity metrics, `combined_similarity`, match strategies |
| `app/etl/loader.py` | snapshot upserts, dimension resolution, aggregates, resilience support |
| `tests/test_cleaning.py` | cleaner unit tests |
| `tests/test_dedupe.py` | dedupe + similarity tests |
| `tests/test_pipeline_resilience.py` | loader/pipeline resilience under failures and retries |

## 6. Responsibilities (from `app/core/team.py`)

- 29-step product-name/category normalisation engine
- 18+ currency price parsing + offline FX to USD
- 4-signal fuzzy dedupe (fingerprint + blocking + similarity)
- Rating/availability vocabularies

## 7. Verify his layer

```bash
cd project
source .venv/bin/activate
pytest tests/test_cleaning.py tests/test_dedupe.py tests/test_pipeline_resilience.py -q
```
