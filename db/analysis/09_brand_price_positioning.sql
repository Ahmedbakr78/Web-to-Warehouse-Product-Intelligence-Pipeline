-- ============================================================================
--  09 · Brand price positioning
--  Which brands price above or below the market, and do they earn it in rating?
--  Bind parameters: :row_limit (default 25)
-- ============================================================================
SELECT brand,
       category_name,
       product_count,
       ROUND(CAST(avg_price_usd AS DECIMAL(24,6)), 2)            AS avg_price_usd,
       ROUND(CAST(avg_rating AS DECIMAL(24,6)), 2)               AS avg_rating,
       ROUND(CAST(avg_price_usd / NULLIF((SELECT AVG(price_usd) FROM vw_product_current), 0)
                 AS DECIMAL(24,6)), 2)                           AS price_index_vs_market
FROM vw_brand_summary
WHERE product_count >= 3
ORDER BY product_count DESC
LIMIT :row_limit;
