-- ============================================================================
--  11 · Rating value: best-rated products priced below their category average
--  Value picks a shopper would shortlist: highly rated, cheaper than peers.
--  Bind parameters: :row_limit (default 25)
-- ============================================================================
SELECT canonical_name,
       brand,
       category_name,
       ROUND(CAST(price_usd AS DECIMAL(24,6)), 2)   AS price_usd,
       ROUND(CAST(rating AS DECIMAL(24,6)), 2)      AS rating,
       source_code
FROM vw_product_current
WHERE rating >= 4.0
  AND price_usd < (
      SELECT AVG(price_usd) FROM vw_product_current AS peer
      WHERE peer.category_name = vw_product_current.category_name
  )
ORDER BY rating DESC, price_usd ASC
LIMIT :row_limit;
