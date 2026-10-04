-- ============================================================================
--  02 · New product discovery
--  What entered the market, who sells it and at what price?
--  Bind parameters: :days (default 30)
-- ============================================================================
SELECT n.product_id,
       n.canonical_name,
       n.brand,
       n.category_name,
       n.source_code,
       n.price_usd                       AS first_seen_price_usd,
       n.currency,
       n.rating,
       n.availability,
       n.first_seen_at,
       n.full_date                       AS first_seen_date,
       c.match_status                    AS catalog_status,
       c.price_gap_pct                   AS price_gap_pct
FROM vw_new_products n
LEFT JOIN vw_catalog_reconciliation c ON c.product_id = n.product_id
WHERE n.first_seen_at >= :since
ORDER BY n.first_seen_at DESC
LIMIT :row_limit;

-- Which categories attract the most new listings?
SELECT category_name,
       COUNT(*)  AS new_products,
       MIN(first_seen_at) AS first_arrival,
       MAX(first_seen_at) AS latest_arrival
FROM vw_new_products
WHERE first_seen_at >= :since
GROUP BY category_name
ORDER BY new_products DESC, category_name
LIMIT :row_limit;
