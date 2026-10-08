-- ============================================================================
--  12 · Discount depth leaders
--  Where are the genuine was/now bargains, and which categories discount hardest?
--  Bind parameters: :row_limit (default 25)
-- ============================================================================
SELECT canonical_name,
       brand,
       category_name,
       ROUND(CAST(price_usd AS DECIMAL(24,6)), 2)      AS price_usd,
       ROUND(CAST(list_price AS DECIMAL(24,6)), 2)     AS list_price,
       ROUND(CAST(discount_pct AS DECIMAL(24,6)), 1)   AS discount_pct,
       source_code
FROM vw_product_current
WHERE discount_pct > 0
ORDER BY discount_pct DESC
LIMIT :row_limit;
