-- ============================================================================
--  03 · Removed product analysis
--  What disappeared from the sources (delisted, out of circulation, stock-out)?
--  Bind parameters: :days (default 90)
-- ============================================================================
SELECT r.product_id,
       r.canonical_name,
       r.brand,
       r.category_name,
       r.source_code,
       r.days_missing,
       r.removed_date,
       r.last_known_price_usd,
       r.last_known_rating
FROM vw_removed_products r
WHERE r.detected_at >= :since
ORDER BY r.detected_at DESC
LIMIT :row_limit;

-- Value at risk: the removed assortment measured by its last known price.
SELECT category_name,
       COUNT(*) AS removed_products,
       ROUND(CAST(SUM(last_known_price_usd) AS DECIMAL(24,6)), 2) AS last_known_value_usd,
       ROUND(CAST(AVG(last_known_price_usd) AS DECIMAL(24,6)), 2) AS avg_price_usd
FROM vw_removed_products
WHERE detected_at >= :since
GROUP BY category_name
ORDER BY removed_products DESC
LIMIT :row_limit;
