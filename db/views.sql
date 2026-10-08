-- =====================================================================================
--  Analytical views (portable SQL: PostgreSQL 12+, MySQL 8+, SQLite 3.35+)
--  Created by app/etl/bootstrap.py -> apply_views()
--  Design: star schema (dim_* / fact_*) + change-feed tables (chg_*) exposed as views.
-- =====================================================================================

-- -------------------------------------------------------------------------------------
-- 1. Current state: one row per active product with its latest observation.
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_product_current AS
SELECT p.product_id,
       p.canonical_name,
       p.display_name,
       p.normalized_name,
       p.brand,
       p.category_id,
       c.name       AS category_name,
       c.path       AS category_path,
       p.product_url,
       p.image_url,
       p.availability,
       p.is_active,
       p.first_seen_at,
       p.last_seen_at,
       p.observation_count,
       p.match_strategy,
       p.match_score,
       s.snapshot_id,
       s.run_id,
       s.captured_at,
       s.price,
       s.list_price,
       s.currency,
       s.price_usd,
       s.discount_pct,
       s.rating,
       s.rating_count,
       s.in_stock,
       s.price_change_abs,
       s.price_change_pct,
       s.source_code
FROM dim_product p
LEFT JOIN dim_category c ON c.category_id = p.category_id
LEFT JOIN fact_price_snapshot s ON s.snapshot_id = (
    SELECT MAX(s2.snapshot_id)
    FROM fact_price_snapshot s2
    WHERE s2.product_id = p.product_id AND s2.source_code = p.source_code
);

-- -------------------------------------------------------------------------------------
-- 2. Price history per product (time series ready for charts).
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_price_history AS
SELECT s.snapshot_id,
       s.product_id,
       p.canonical_name,
       p.brand,
       p.category_id,
       c.name AS category_name,
       s.source_code,
       s.run_id,
       s.date_id,
       d.full_date,
       d.year,
       d.month,
       s.captured_at,
       s.price,
       s.price_usd,
       s.currency,
       s.fx_rate_to_usd,
       s.rating,
       s.availability,
       s.is_first_sighting,
       s.price_change_abs,
       s.price_change_pct
FROM fact_price_snapshot s
JOIN dim_product p ON p.product_id = s.product_id
LEFT JOIN dim_category c ON c.category_id = p.category_id
LEFT JOIN dim_date d ON d.date_id = s.date_id;

-- -------------------------------------------------------------------------------------
-- 3. Price movement over a rolling window (LAG based, per product+source).
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_price_movements AS
SELECT h.product_id,
       h.canonical_name,
       h.category_name,
       h.source_code,
       h.full_date,
       h.captured_at,
       h.price_usd,
       LAG(h.price_usd) OVER (PARTITION BY h.product_id, h.source_code ORDER BY h.captured_at) AS prev_price_usd,
       h.price_usd - LAG(h.price_usd) OVER (PARTITION BY h.product_id, h.source_code ORDER BY h.captured_at) AS change_abs,
       CASE
           WHEN LAG(h.price_usd) OVER (PARTITION BY h.product_id, h.source_code ORDER BY h.captured_at) IS NULL
             OR LAG(h.price_usd) OVER (PARTITION BY h.product_id, h.source_code ORDER BY h.captured_at) = 0
           THEN NULL
           ELSE ROUND((h.price_usd - LAG(h.price_usd) OVER (PARTITION BY h.product_id, h.source_code ORDER BY h.captured_at))
                      / ABS(LAG(h.price_usd) OVER (PARTITION BY h.product_id, h.source_code ORDER BY h.captured_at)) * 100, 4)
       END AS change_pct
FROM vw_price_history h;

-- -------------------------------------------------------------------------------------
-- 4. Change feed: every detected price change joined to product context.
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_price_changes AS
SELECT ch.change_id,
       ch.product_id,
       p.canonical_name,
       p.brand,
       p.category_id,
       c.name AS category_name,
       ch.source_code,
       ch.run_id,
       ch.date_id,
       d.full_date,
       ch.previous_price,
       ch.new_price,
       ch.previous_price_usd,
       ch.new_price_usd,
       ch.change_abs,
       ch.change_pct,
       ch.direction,
       ch.magnitude_band,
       ch.is_significant,
       ch.currency,
       ch.detected_at
FROM chg_price_change ch
JOIN dim_product p ON p.product_id = ch.product_id
LEFT JOIN dim_category c ON c.category_id = p.category_id
LEFT JOIN dim_date d ON d.date_id = ch.date_id;

-- -------------------------------------------------------------------------------------
-- 5. Product lifecycle feed (new / removed / recurring / category changes).
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_product_events AS
SELECT e.event_id,
       e.product_id,
       p.canonical_name,
       p.brand,
       e.source_code,
       e.run_id,
       e.date_id,
       d.full_date,
       e.event_type,
       e.severity,
       e.old_value,
       e.new_value,
       e.old_category_id,
       e.new_category_id,
       e.days_missing,
       e.detected_at,
       p.is_active
FROM chg_product_event e
JOIN dim_product p ON p.product_id = e.product_id
LEFT JOIN dim_date d ON d.date_id = e.date_id;

-- -------------------------------------------------------------------------------------
-- 6. Newly discovered products (market entrants the catalog does not know yet).
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_new_products AS
SELECT p.product_id,
       p.canonical_name,
       p.brand,
       c.name AS category_name,
       p.source_code,
       p.product_url,
       s.price,
       s.price_usd,
       s.currency,
       s.rating,
       s.availability,
       p.first_seen_at,
       e.date_id,
       d.full_date AS first_seen_date,
       d.full_date,
       e.detected_at,
       s.price_usd AS first_seen_price_usd
FROM chg_product_event e
JOIN dim_product p ON p.product_id = e.product_id
LEFT JOIN dim_category c ON c.category_id = p.category_id
LEFT JOIN fact_price_snapshot s ON s.product_id = p.product_id AND s.run_id = e.run_id
LEFT JOIN dim_date d ON d.date_id = e.date_id
WHERE e.event_type = 'new';

-- -------------------------------------------------------------------------------------
-- 7. Products that disappeared from a source (stock-outs or delistings).
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_removed_products AS
SELECT p.product_id,
       p.canonical_name,
       p.brand,
       c.name AS category_name,
       e.source_code,
       e.old_value,
       e.days_missing,
       e.detected_at,
       d.full_date AS removed_date,
       s.price_usd AS last_known_price_usd,
       s.rating AS last_known_rating
FROM chg_product_event e
JOIN dim_product p ON p.product_id = e.product_id
LEFT JOIN dim_category c ON c.category_id = p.category_id
LEFT JOIN dim_date d ON d.date_id = e.date_id
LEFT JOIN fact_price_snapshot s ON s.snapshot_id = (
    SELECT MAX(s2.snapshot_id) FROM fact_price_snapshot s2 WHERE s2.product_id = p.product_id
)
WHERE e.event_type = 'removed';

-- -------------------------------------------------------------------------------------
-- 8. Products whose category changed over time (assortment drift).
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_category_changes AS
SELECT e.event_id,
       e.product_id,
       p.canonical_name,
       e.source_code,
       e.old_category_id,
       oc.name AS old_category,
       e.new_category_id,
       nc.name AS new_category,
       e.detected_at,
       d.full_date AS change_date,
       d.full_date
FROM chg_product_event e
JOIN dim_product p ON p.product_id = e.product_id
LEFT JOIN dim_category oc ON oc.category_id = e.old_category_id
LEFT JOIN dim_category nc ON nc.category_id = e.new_category_id
LEFT JOIN dim_date d ON d.date_id = e.date_id
WHERE e.event_type = 'category_changed';

-- -------------------------------------------------------------------------------------
-- 9. Category price index (daily avg / min / max / volatility per category).
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_category_price_index AS
SELECT s.date_id,
       d.full_date,
       p.category_id,
       c.name AS category_name,
       COUNT(*) AS observation_count,
       ROUND(CAST(AVG(s.price_usd) AS DECIMAL(24,6)), 4) AS avg_price_usd,
       ROUND(CAST(MIN(s.price_usd) AS DECIMAL(24,6)), 4) AS min_price_usd,
       ROUND(CAST(MAX(s.price_usd) AS DECIMAL(24,6)), 4) AS max_price_usd,
       ROUND(CAST(AVG(s.rating) AS DECIMAL(24,6)), 4) AS avg_rating,
       -- Portable population variance (SQLite has no STDDEV, MySQL/PG differ in name).
       ROUND(CAST(SQRT(CASE WHEN (AVG(s.price_usd) * AVG(s.price_usd) - AVG(s.price_usd * s.price_usd)) < 0
                                   THEN 0
                                   ELSE (AVG(s.price_usd) * AVG(s.price_usd) - AVG(s.price_usd * s.price_usd))
                              END) AS DECIMAL(24,6)), 4) AS price_stddev,
       COUNT(DISTINCT p.product_id) AS distinct_products
FROM fact_price_snapshot s
JOIN dim_product p ON p.product_id = s.product_id
LEFT JOIN dim_category c ON c.category_id = p.category_id
LEFT JOIN dim_date d ON d.date_id = s.date_id
GROUP BY s.date_id, d.full_date, p.category_id, c.name;

-- -------------------------------------------------------------------------------------
-- 10. Brand leaderboard (avg price, rating, product count, share of category).
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_brand_summary AS
SELECT p.brand,
       c.name AS category_name,
       COUNT(DISTINCT p.product_id) AS product_count,
       ROUND(CAST(AVG(s.price_usd) AS DECIMAL(24,6)), 4) AS avg_price_usd,
       ROUND(CAST(MIN(s.price_usd) AS DECIMAL(24,6)), 4) AS min_price_usd,
       ROUND(CAST(MAX(s.price_usd) AS DECIMAL(24,6)), 4) AS max_price_usd,
       ROUND(CAST(AVG(s.rating) AS DECIMAL(24,6)), 4) AS avg_rating,
       SUM(CASE WHEN s.in_stock THEN 1 ELSE 0 END) AS in_stock_observations,
       MAX(s.captured_at) AS last_seen_at
FROM dim_product p
JOIN fact_price_snapshot s ON s.product_id = p.product_id
LEFT JOIN dim_category c ON c.category_id = p.category_id
WHERE p.brand IS NOT NULL
GROUP BY p.brand, c.name;

-- -------------------------------------------------------------------------------------
-- 11. Source coverage & reliability.
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_source_coverage AS
SELECT src.source_code,
       src.name AS source_name,
       src.kind,
       src.enabled,
       src.rate_limit_per_minute,
       COUNT(DISTINCT s.product_id) AS products_seen,
       COUNT(s.snapshot_id)          AS observations,
       ROUND(CAST(AVG(s.price_usd) AS DECIMAL(24,6)), 4)    AS avg_price_usd,
       ROUND(CAST(AVG(s.rating) AS DECIMAL(24,6)), 4)       AS avg_rating,
       MAX(s.captured_at)            AS last_observation_at,
       src.success_rate_pct,
       src.avg_duration_seconds
FROM dim_source src
LEFT JOIN fact_price_snapshot s ON s.source_code = src.source_code
GROUP BY src.source_code, src.name, src.kind, src.enabled, src.rate_limit_per_minute,
         src.success_rate_pct, src.avg_duration_seconds;

-- -------------------------------------------------------------------------------------
-- 12. Data-quality summary for the most recent run.
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_quality_latest AS
SELECT q.run_id,
       r.status        AS run_status,
       r.target_database,
       r.started_at,
       r.dq_score,
       SUM(CASE WHEN q.status = 'pass' THEN 1 ELSE 0 END) AS rules_passed,
       SUM(CASE WHEN q.status = 'warn' THEN 1 ELSE 0 END) AS rules_warned,
       SUM(CASE WHEN q.status = 'fail' THEN 1 ELSE 0 END) AS rules_failed,
       COUNT(*) AS rules_total
FROM dq_rule_result q
JOIN etl_run r ON r.run_id = q.run_id
GROUP BY q.run_id, r.status, r.target_database, r.started_at, r.dq_score;

-- -------------------------------------------------------------------------------------
-- 13. Pipeline health per run (single row = one dashboard card).
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_pipeline_health AS
SELECT r.run_id,
       r.status,
       -- ``trigger`` is a reserved word in MySQL 8.4, so it is aliased here and the
       -- API re-exposes it as ``trigger`` for API consumers.
       r.trigger AS run_trigger,
       r.target_database,
       r.dag_id,
       r.task_id,
       r.run_key,
       r.started_at,
       r.finished_at,
       r.duration_ms,
       r.records_extracted,
       r.records_valid,
       r.records_rejected,
       r.records_inserted,
       r.records_updated,
       r.duplicates_merged,
       r.new_products,
       r.price_changes,
       r.removed_products,
       r.catalog_matched,
       r.dq_score,
       CASE
           WHEN r.records_extracted > 0
           THEN ROUND(CAST((r.records_valid / r.records_extracted) * 100 AS DECIMAL(24,6)), 2)
           ELSE 0
       END AS yield_pct,
       r.error_message
FROM etl_run r;

-- -------------------------------------------------------------------------------------
-- 14. Catalog reconciliation report (scraped vs internal catalog).
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_catalog_reconciliation AS
SELECT f.match_id,
       f.run_id,
       f.catalog_sku,
       cp.name          AS catalog_name,
       cp.brand         AS catalog_brand,
       cp.category      AS catalog_category,
       cp.list_price    AS catalog_price,
       cp.supplier,
       f.product_id,
       p.canonical_name AS scraped_name,
       p.brand          AS scraped_brand,
       c.name           AS scraped_category,
       f.scraped_price  AS scraped_price_usd,
       f.price_gap_abs,
       f.price_gap_pct,
       f.match_status,
       f.match_strategy,
       f.similarity_score,
       f.category_match,
       f.brand_match,
       f.is_price_mismatch,
       f.matched_at
FROM fact_catalog_snapshot f
LEFT JOIN catalog_product cp ON cp.sku = f.catalog_sku
LEFT JOIN dim_product p ON p.product_id = f.product_id
LEFT JOIN dim_category c ON c.category_id = p.category_id;

-- -------------------------------------------------------------------------------------
-- 15. Top movers: biggest price increases/decreases (usable for alerting).
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_top_movers AS
SELECT pc.product_id,
       pc.canonical_name,
       pc.category_name,
       pc.source_code,
       pc.full_date,
       pc.previous_price,
       pc.new_price,
       pc.change_abs,
       pc.change_pct,
       pc.direction,
       pc.magnitude_band,
       pc.is_significant
FROM vw_price_changes pc
WHERE pc.change_pct IS NOT NULL;

-- -------------------------------------------------------------------------------------
-- 16. Availability outlook per category (in-stock ratio).
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_availability_summary AS
SELECT p.category_id,
       c.name AS category_name,
       COUNT(*) AS observations,
       SUM(CASE WHEN s.in_stock THEN 1 ELSE 0 END) AS in_stock_count,
       ROUND(CAST(100.0 * SUM(CASE WHEN s.in_stock THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0) AS DECIMAL(24,6)), 2) AS in_stock_pct,
       SUM(CASE WHEN s.availability = 'out_of_stock' THEN 1 ELSE 0 END) AS out_of_stock_count
FROM fact_price_snapshot s
JOIN dim_product p ON p.product_id = s.product_id
LEFT JOIN dim_category c ON c.category_id = p.category_id
GROUP BY p.category_id, c.name;

-- -------------------------------------------------------------------------------------
-- 17. Daily KPI rollup used by the dashboard trend chart.
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_daily_kpis AS
SELECT s.date_id,
       d.full_date,
       COUNT(DISTINCT s.product_id) AS products_observed,
       COUNT(s.snapshot_id)         AS observations,
       ROUND(CAST(AVG(s.price_usd) AS DECIMAL(24,6)), 4)   AS avg_price_usd,
       ROUND(CAST(AVG(s.rating) AS DECIMAL(24,6)), 4)      AS avg_rating,
       ROUND(CAST(100.0 * SUM(CASE WHEN s.in_stock THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0) AS DECIMAL(24,6)), 2) AS in_stock_pct
FROM fact_price_snapshot s
LEFT JOIN dim_date d ON d.date_id = s.date_id
GROUP BY s.date_id, d.full_date;

-- -------------------------------------------------------------------------------------
-- 18. Compliance audit view (every outbound request the pipeline made).
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_http_audit AS
SELECT h.log_id,
       h.run_id,
       h.source_code,
       h.method,
       h.url,
       h.host,
       h.status_code,
       h.elapsed_ms,
       h.response_bytes,
       h.robots_allowed,
       h.robots_rule,
       h.from_cache,
       h.retry_count,
       h.error,
       h.requested_at
FROM ingestion_http_log h;

-- -------------------------------------------------------------------------------------
-- 19. Product search index (normalised, deduplicated, inactive rows excluded).
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_product_index AS
SELECT p.product_id,
       p.canonical_name,
       p.normalized_name,
       p.brand,
       c.name AS category_name,
       c.path AS category_path,
       p.availability,
       p.is_active,
       p.observation_count,
       p.first_seen_at,
       p.last_seen_at,
       p.source_code,
       p.product_url,
       p.image_url,
       p.current_price,
       p.current_rating
FROM dim_product p
LEFT JOIN dim_category c ON c.category_id = p.category_id;

-- -------------------------------------------------------------------------------------
-- 20. Category tree with live counts (for the taxonomy explorer).
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_category_tree AS
SELECT c.category_id,
       c.name,
       c.slug,
       c.level,
       c.path,
       c.parent_id,
       c.product_count,
       (SELECT COUNT(*) FROM dim_product p2 WHERE p2.category_id = c.category_id AND p2.is_active) AS active_products,
       (SELECT ROUND(CAST(AVG(s.price_usd) AS DECIMAL(24,6)), 2) FROM fact_price_snapshot s WHERE s.product_id IN
            (SELECT p3.product_id FROM dim_product p3 WHERE p3.category_id = c.category_id AND p3.is_active)) AS avg_price_usd
FROM dim_category c;

-- -------------------------------------------------------------------------------------
-- 21. Price volatility per product+source (range and portable stddev).
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_price_volatility AS
SELECT s.product_id,
       p.canonical_name,
       p.brand,
       c.name AS category_name,
       s.source_code,
       COUNT(*) AS observations,
       ROUND(CAST(AVG(s.price_usd) AS DECIMAL(24,6)), 4) AS avg_price_usd,
       ROUND(CAST(MIN(s.price_usd) AS DECIMAL(24,6)), 4) AS min_price_usd,
       ROUND(CAST(MAX(s.price_usd) AS DECIMAL(24,6)), 4) AS max_price_usd,
       CASE
           WHEN AVG(s.price_usd) IS NULL OR AVG(s.price_usd) = 0 THEN NULL
           ELSE ROUND(CAST(100.0 * (MAX(s.price_usd) - MIN(s.price_usd)) / AVG(s.price_usd) AS DECIMAL(24,6)), 2)
       END AS range_pct,
       -- Portable population stddev (same derivation as vw_category_price_index:
       -- SQLite has no STDDEV, MySQL/PG differ in name).
       ROUND(CAST(SQRT(CASE WHEN (AVG(s.price_usd) * AVG(s.price_usd) - AVG(s.price_usd * s.price_usd)) < 0
                                   THEN 0
                                   ELSE (AVG(s.price_usd) * AVG(s.price_usd) - AVG(s.price_usd * s.price_usd))
                              END) AS DECIMAL(24,6)), 4) AS price_stddev,
       SUM(CASE WHEN s.price_change_pct IS NOT NULL THEN 1 ELSE 0 END) AS changes_observed,
       MAX(s.captured_at) AS last_observation_at
FROM fact_price_snapshot s
JOIN dim_product p ON p.product_id = s.product_id
LEFT JOIN dim_category c ON c.category_id = p.category_id
WHERE s.price_usd IS NOT NULL
GROUP BY s.product_id, p.canonical_name, p.brand, c.name, s.source_code;

-- -------------------------------------------------------------------------------------
-- 22. Discount leaders: current products with the deepest list-price discounts.
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_discount_leaders AS
SELECT product_id,
       canonical_name,
       brand,
       category_name,
       source_code,
       price,
       list_price,
       currency,
       price_usd,
       discount_pct,
       ROUND(CAST(list_price - price AS DECIMAL(24,6)), 2) AS savings_amount,
       availability,
       in_stock,
       last_seen_at
FROM vw_product_current
WHERE discount_pct IS NOT NULL AND discount_pct > 0;

-- -------------------------------------------------------------------------------------
-- 23. Rating leaders: best-rated products with a vote-damped score.
-- -------------------------------------------------------------------------------------
CREATE VIEW vw_rating_leaders AS
SELECT product_id,
       canonical_name,
       brand,
       category_name,
       source_code,
       price_usd,
       rating,
       rating_count,
       -- Damped score: a lone 5-star review must not outrank 500 4.6-star ones.
       ROUND(CAST(rating * rating_count / (rating_count + 10) AS DECIMAL(24,6)), 4) AS damped_score,
       availability,
       in_stock,
       observation_count,
       last_seen_at
FROM vw_product_current
WHERE rating IS NOT NULL;