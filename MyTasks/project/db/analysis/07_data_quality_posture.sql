-- ============================================================================
--  07 · Data quality posture
--  How trustworthy is the warehouse, per dimension and per rule?
-- ============================================================================
SELECT q.run_id,
       r.target_database,
       r.status                           AS run_status,
       r.started_at,
       r.dq_score,
       q.dimension,
       q.severity,
       COUNT(*)                           AS evaluations,
       SUM(CASE WHEN q.status = 'pass' THEN 1 ELSE 0 END) AS passed,
       SUM(CASE WHEN q.status = 'warn' THEN 1 ELSE 0 END) AS warned,
       SUM(CASE WHEN q.status = 'fail' THEN 1 ELSE 0 END) AS failed,
       SUM(q.records_checked)              AS records_checked,
       SUM(q.records_failed)               AS records_failed
FROM dq_rule_result q
JOIN etl_run r ON r.run_id = q.run_id
GROUP BY q.run_id, r.target_database, r.status, r.started_at, r.dq_score, q.dimension, q.severity
ORDER BY r.started_at DESC, q.dimension;

-- Rules that consistently find problems (the ones that need engineering attention).
SELECT rule_code,
       rule_name,
       dimension,
       severity,
       COUNT(*)                           AS evaluations,
       SUM(CASE WHEN status = 'fail' THEN 1 ELSE 0 END) AS failures,
       SUM(CASE WHEN status = 'warn' THEN 1 ELSE 0 END) AS warnings,
       ROUND(CAST(100.0 * SUM(CASE WHEN status = 'fail' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0) AS DECIMAL(24,6)), 2) AS failure_rate_pct
FROM dq_rule_result
GROUP BY rule_code, rule_name, dimension, severity
ORDER BY failure_rate_pct DESC, evaluations DESC;
