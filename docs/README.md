# Documentation Index

Web-to-Warehouse Product Intelligence Pipeline — DEPI graduation project (Data Engineering track).
Twenty documents covering proposal, planning, requirements, design, implementation evidence and
evaluation. Every diagram is Mermaid (rendered natively by GitHub); every number is reproducible with
the command cited beside it.

| # | Document | What it covers |
| --- | --- | --- |
| 01 | [Project Proposal](01_project_proposal.md) | Problem, objectives, scope, stakeholders, acceptance criteria, effort and budget, ethical and legal position, assumptions |
| 02 | [Project Plan](02_project_plan.md) | 12-week Gantt chart, milestones, deliverables matrix, resource allocation, sprint plan |
| 03 | [Task Assignment and Roles](03_roles_and_responsibilities.md) | Team roles, RACI for deliverables and decisions, communication plan, hours-log template |
| 04 | [Risk Assessment](04_risk_assessment.md) | 20-risk register with heat map, treatments, contingencies and the issues that materialised |
| 05 | [KPIs](05_kpis.md) | 20 KPIs with runnable SQL, targets versus measured values, API latency harness |
| 06 | [Literature Review](06_literature_review.md) | Six themes, 39 sources with verification status, synthesis and research gaps |
| 07 | [Requirements Gathering](07_requirements_gathering.md) | Stakeholders, 10 user stories with Given/When/Then, 20 use cases, 58 FRs, 26 NFRs, traceability |
| 08 | [System Analysis and Design](08_system_analysis_design.md) | Use-case diagram, architecture diagram, style and rationale |
| 09 | [Database Design](09_database_design.md) | Generated 23-table ERD, logical versus physical schema, normalisation, indexing, retention, dialect types |
| 10 | [Data Flow Diagrams](10_data_flow_diagrams.md) | Level 0/1/2 DFDs, data dictionary, control flows |
| 11 | [Behaviour Diagrams](11_behaviour_diagrams.md) | Sequence, activity, three state diagrams, class diagram |
| 12 | [UI/UX Design](12_ui_ux_design.md) | 12 screen wireframes, design system with contrast ratios, WCAG 2.1 AA, breakpoints, motion policy |
| 13 | [Deployment](13_deployment.md) | Stack, deployment and component diagrams, environment matrix, Compose services, ports, secrets, backup, scaling, CI/CD |
| 14 | [API Documentation](14_api_documentation.md) | Auth flow, role matrix, all 104 operations, worked examples in curl/Python/JS, errors, versioning |
| 15 | [Testing Strategy](15_testing_strategy.md) | Test pyramid, 100-case plan, UAT scenarios, coverage targets, quality gates, defect management |
| 16 | [User Manual](16_user_manual.md) | Sign-in, every screen, filters, exports, saved views, alerts, admin, troubleshooting, FAQ |
| 17 | [Technical Documentation](17_technical_documentation.md) | Module map, four key algorithms, every configuration variable, six-step source extension, performance and security |
| 18 | [Presentation Outline](18_presentation_outline.md) | 18-slide defence deck, Q&A preparation, three-minute demo script, rehearsal and fallback plans |
| 19 | [Feature Inventory](19_feature_list.md) | 226 features in 14 areas, each with a description and a file reference |
| 20 | [Feedback and Improvements](20_literature_feedback_and_improvements.md) | Lecturer feedback template, 32 prioritised improvements, self-assessment and rubric |

## Measured facts referenced throughout

| Fact | Value |
| --- | --- |
| Physical tables / analytical views | 23 / 20 (on PostgreSQL 16.15 and MySQL 8.4.11) |
| REST operations | 104 documented in 15 routers |
| Data-quality rules / dimensions | 12 / 6, score 98.26 on both engines |
| Ingestion sources | 5 (3 APIs, 1 HTML scraper, 1 offline synthetic) |
| Demo dataset | 60 products, 8,182 price snapshots, 8,047 price changes, 8,199 lifecycle events over 150 days |
| Measured live run | 57 snapshots, 48 price changes, 6 new products, 39/57 catalog SKUs matched (68.42 %), DQ 98.26, ≈ 3.5 s |
| Reconciliation optimisation | 2,975 ms → 104 ms (29×) with identical results |
| API latency | p95 ≤ 38.2 ms across 12 read endpoints |
| API regression suite | 78/78 checks pass |
| Demo accounts | `admin@example.com` / `Admin@12345`, `analyst@example.com` / `Analyst@12345`, `viewer@example.com` / `Viewer@12345` |

## Quick commands

```bash
make install && make env          # environment
make up-db && make db-wait        # PostgreSQL 16 + MySQL 8.4
make bootstrap                    # 23 tables + 20 views + reference data
make demo-postgres                # demo dataset
make run-pipeline                 # one full pipeline run
make verify-dialects              # cross-dialect verification
make serve                        # API on http://localhost:8000/docs
.venv/bin/python scripts/api_smoke.py     # 78-check regression suite
make help                         # all 30+ targets
```

## Rendering the diagrams

GitHub renders Mermaid natively, so no build step is required. To export SVGs:

```bash
make docs-render      # writes docs/diagrams/out/*.svg
make docs-serve       # serves docs/ on http://localhost:8001
```