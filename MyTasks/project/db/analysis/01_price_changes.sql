-- ============================================================================
--  01 · Price change analysis
--  Which products moved, in which direction, and by how much?
--  Bind parameters: :days (default 30)
-- ============================================================================
SELECT pc.full_date,
       p.product_id,
       p.canonical_name,
       p.brand,
       c.name                        AS category_name,
       pc.source_code,
       pc.previous_price,
       pc.new_price,
       pc.change_abs,
       pc.change_pct,
       pc.direction,
       pc.magnitude_band,
       pc.is_significant,
       pc.currency
FROM vw_price_changes pc
JOIN dim_product p ON p.product_id = pc.product_id
LEFT JOIN dim_category c ON c.category_id = p.category_id
WHERE pc.full_date >= :since
ORDER BY ABS(pc.change_pct) DESC
LIMIT :row_limit;

-- Summary: volume and magnitude of movement in the window.
SELECT direction,
       COUNT(*)                              AS events,
       SUM(CASE WHEN is_significant THEN 1 ELSE 0 END) AS significant_events,
       ROUND(CAST(AVG(ABS(change_pct)) AS DECIMAL(24,6)), 2) AS avg_abs_change_pct,
       ROUND(CAST(MAX(ABS(change_pct)) AS DECIMAL(24,6)), 2) AS max_abs_change_pct
FROM vw_price_changes
WHERE full_date >= :since
GROUP BY direction
ORDER BY events DESC;
