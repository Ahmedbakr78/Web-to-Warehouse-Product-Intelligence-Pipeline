-- ============================================================================
--  06 · Internal catalog reconciliation and price-gap analysis
--  Are our list prices competitive? Which SKUs are missing from the market?
--  Bind parameters: :gap_pct (default 1.0)
-- ============================================================================
SELECT catalog_sku,
       catalog_name,
       catalog_brand,
       catalog_category,
       supplier,
       catalog_price,
       product_id,
       scraped_name,
       scraped_category,
       scraped_price_usd,
       price_gap_abs,
       price_gap_pct,
       CASE
           WHEN price_gap_pct < 0 THEN 'we_are_dearer'
           WHEN price_gap_pct > 0 THEN 'we_are_cheaper'
           ELSE 'parity'
       END                       AS price_position,
       match_status,
       match_strategy,
       similarity_score,
       matched_at
FROM vw_catalog_reconciliation
WHERE is_price_mismatch
  AND ABS(price_gap_pct) >= :gap_pct
ORDER BY ABS(price_gap_pct) DESC
LIMIT :row_limit;

-- Coverage and match quality per supplier.
SELECT supplier,
       COUNT(*)                                                  AS skus,
       SUM(CASE WHEN match_status = 'matched' THEN 1 ELSE 0 END) AS matched,
       SUM(CASE WHEN match_status = 'unmatched' THEN 1 ELSE 0 END) AS unmatched,
       SUM(CASE WHEN is_price_mismatch THEN 1 ELSE 0 END)        AS price_mismatches,
       ROUND(CAST(AVG(price_gap_pct) AS DECIMAL(24,6)), 2)      AS avg_price_gap_pct,
       ROUND(CAST(AVG(similarity_score) AS DECIMAL(24,6)), 4)   AS avg_similarity
FROM vw_catalog_reconciliation
GROUP BY supplier
ORDER BY skus DESC;
