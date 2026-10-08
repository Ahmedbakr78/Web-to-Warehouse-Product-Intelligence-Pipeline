-- ============================================================================
--  13 · Category concentration: does one brand own the shelf?
--  Top-brand share per category (HHI-lite): 100% means a single-brand shelf.
--  Bind parameters: :row_limit (default 25)
-- ============================================================================
SELECT category_name,
       SUM(product_count)                                   AS products,
       MAX(product_count)                                   AS top_brand_products,
       ROUND(CAST(MAX(product_count) * 100.0 / NULLIF(SUM(product_count), 0)
                 AS DECIMAL(24,6)), 1)                      AS top_brand_share_pct,
       (SELECT brand FROM vw_brand_summary AS lead
        WHERE lead.category_name = vw_brand_summary.category_name
        ORDER BY lead.product_count DESC LIMIT 1)           AS top_brand
FROM vw_brand_summary
GROUP BY category_name
HAVING SUM(product_count) >= 5
ORDER BY top_brand_share_pct DESC
LIMIT :row_limit;
