-- ============================================================================
--  15 · Stockout risk by category
--  Where is availability thinnest relative to observed demand?
--  Bind parameters: :row_limit (default 25)
-- ============================================================================
SELECT category_name,
       observations,
       in_stock_count,
       out_of_stock_count,
       ROUND(CAST(in_stock_pct AS DECIMAL(24,6)), 1)   AS in_stock_pct,
       ROUND(CAST(100.0 - in_stock_pct AS DECIMAL(24,6)), 1) AS stockout_pct
FROM vw_availability_summary
WHERE observations >= 10
  AND (in_stock_count + out_of_stock_count) > 0
ORDER BY stockout_pct DESC, observations DESC
LIMIT :row_limit;
