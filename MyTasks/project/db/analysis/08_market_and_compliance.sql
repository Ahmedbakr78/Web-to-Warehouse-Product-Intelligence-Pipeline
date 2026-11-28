-- ============================================================================
--  08 · Market overview + ingestion compliance evidence
--  One query for the market picture, one for "did we crawl politely?".
-- ============================================================================
-- Market overview per source.
SELECT source_code,
       source_name,
       kind,
       enabled,
       products_seen,
       observations,
       ROUND(CAST(avg_price_usd AS DECIMAL(24,6)), 2) AS avg_price_usd,
       ROUND(CAST(avg_rating  AS DECIMAL(24,6)), 2)  AS avg_rating,
       success_rate_pct,
       avg_duration_seconds,
       last_observation_at
FROM vw_source_coverage
ORDER BY observations DESC;

-- Daily market pulse.
SELECT full_date,
       products_observed,
       observations,
       ROUND(CAST(avg_price_usd AS DECIMAL(24,6)), 2) AS avg_price_usd,
       ROUND(CAST(avg_rating    AS DECIMAL(24,6)), 2) AS avg_rating,
       in_stock_pct
FROM vw_daily_kpis
WHERE full_date >= :since
ORDER BY full_date;

-- Compliance evidence: requests, cache hits and robots.txt decisions.
SELECT source_code,
       host,
       COUNT(*)                                                    AS requests,
       SUM(CASE WHEN robots_allowed THEN 0 ELSE 1 END)             AS blocked_by_robots,
       SUM(CASE WHEN from_cache THEN 1 ELSE 0 END)                AS served_from_cache,
       SUM(CASE WHEN retry_count > 0 THEN 1 ELSE 0 END)            AS retried,
       SUM(response_bytes)                                         AS bytes_received,
       ROUND(CAST(AVG(elapsed_ms) AS DECIMAL(24,6)), 1)           AS avg_elapsed_ms,
       MAX(status_code)                                            AS worst_status
FROM vw_http_audit
WHERE requested_at >= :since
GROUP BY source_code, host
ORDER BY requests DESC;
