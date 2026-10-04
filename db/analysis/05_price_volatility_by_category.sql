-- ============================================================================
--  05 · Price volatility and price index by category
--  How stable are prices, and which categories move the most?
--  Bind parameters: :days (default 60)
-- ============================================================================
SELECT category_name,
       COUNT(DISTINCT full_date)        AS days_observed,
       SUM(observation_count)            AS observations,
       ROUND(CAST(AVG(avg_price_usd) AS DECIMAL(24,6)), 2)  AS avg_price_usd,
       ROUND(CAST(MIN(min_price_usd) AS DECIMAL(24,6)), 2)  AS min_price_usd,
       ROUND(CAST(MAX(max_price_usd) AS DECIMAL(24,6)), 2)  AS max_price_usd,
       ROUND(CAST(AVG(price_stddev) AS DECIMAL(24,6)), 2)   AS avg_daily_stddev,
       ROUND(CAST(AVG(avg_rating) AS DECIMAL(24,6)), 2)     AS avg_rating,
       MAX(distinct_products)            AS widest_assortment
FROM vw_category_price_index
WHERE full_date >= :since
GROUP BY category_name
ORDER BY avg_daily_stddev DESC
LIMIT :row_limit;
