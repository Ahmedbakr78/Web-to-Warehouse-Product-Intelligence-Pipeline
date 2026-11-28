-- ============================================================================
--  10 · Source overlap: products observed by more than one source
--  Proof that dedupe works across feeds: the same canonical product surfacing
--  in two marketplaces. Joins the price fact to the product dimension (both
--  warehouse tables, never the raw landing area).
--  Bind parameters: :row_limit (default 25)
-- ============================================================================
SELECT p.canonical_name,
       p.brand,
       c.name                                             AS category_name,
       COUNT(DISTINCT s.source_code)                      AS sources_covering,
       COUNT(*)                                           AS snapshots,
       ROUND(CAST(MIN(s.price_usd) AS DECIMAL(24,6)), 2)  AS best_price_usd,
       ROUND(CAST(MAX(s.price_usd) AS DECIMAL(24,6)), 2)  AS worst_price_usd
FROM fact_price_snapshot s
JOIN dim_product p ON p.product_id = s.product_id
LEFT JOIN dim_category c ON c.category_id = p.category_id
GROUP BY p.product_id, p.canonical_name, p.brand, c.name
HAVING COUNT(DISTINCT s.source_code) > 1
ORDER BY sources_covering DESC, snapshots DESC
LIMIT :row_limit;
