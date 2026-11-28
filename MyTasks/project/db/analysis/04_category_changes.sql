-- ============================================================================
--  04 · Category change analysis (assortment drift)
--  Which products were re-categorised upstream, and how did the taxonomy move?
--  Bind parameters: :days (default 90)
-- ============================================================================
SELECT cc.full_date                       AS change_date,
       cc.product_id,
       cc.canonical_name,
       cc.source_code,
       cc.old_category,
       cc.new_category
FROM vw_category_changes cc
WHERE cc.detected_at >= :since
ORDER BY cc.detected_at DESC
LIMIT :row_limit;

-- Net assortment movement per category in the window.
SELECT c.name AS category_name,
       COUNT(DISTINCT CASE WHEN e.event_type = 'new' THEN e.product_id END) AS products_added,
       COUNT(DISTINCT CASE WHEN e.event_type = 'removed' THEN e.product_id END) AS products_removed,
       COUNT(DISTINCT CASE WHEN e.event_type = 'category_changed' THEN e.product_id END) AS products_recategorised,
       COUNT(DISTINCT CASE WHEN e.event_type = 'new' THEN e.product_id END)
         - COUNT(DISTINCT CASE WHEN e.event_type = 'removed' THEN e.product_id END) AS net_change
FROM dim_category c
LEFT JOIN dim_product p ON p.category_id = c.category_id
LEFT JOIN chg_product_event e ON e.product_id = p.product_id AND e.detected_at >= :since
GROUP BY c.name
ORDER BY net_change DESC, products_added DESC
LIMIT :row_limit;
