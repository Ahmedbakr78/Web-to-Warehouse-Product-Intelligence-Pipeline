-- ============================================================================
--  14 · New-product velocity
--  How fast is the assortment growing, per day and per category?
--  CAST(x AS DATE) is the one day-cast all three dialects accept.
--  Bind parameters: :since (default 30 days ago), :row_limit (default 25)
-- ============================================================================
SELECT CAST(first_seen_at AS DATE)   AS first_seen_day,
       COUNT(*)                      AS new_products,
       COUNT(DISTINCT category_name) AS categories_touched,
       COUNT(DISTINCT source_code)   AS sources_reporting
FROM vw_new_products
WHERE first_seen_at >= :since
GROUP BY CAST(first_seen_at AS DATE)
ORDER BY first_seen_day DESC
LIMIT :row_limit;
