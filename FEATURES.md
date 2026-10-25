# FEATURES.md — feature → file → status

Status: **DONE** (works and tested) · **TODO (Mx)** (planned in that module, stub file exists) · **STUB** (future scope, file exists, returns 501 / "Coming soon").
Updated after every module.

| Feature | Backend file | Frontend / other file | Status |
|---|---|---|---|
| Project scaffold, run_all, health check | hub/backend/app/main.py, run_all.py | hub/frontend/src/App.jsx | DONE (M0) |
| Models + CSV seed loader | models.py, seed.py, services/institutions.py (normalizer), services/reporters.py (fingerprint) | data/*.csv | DONE (M1) |
| Institution registry, search, name resolver | routers/institutions.py | shared/institution-finder.js | TODO (M2) |
| Login + roles | routers/auth.py | pages/Login.jsx | TODO (M3, cut to dropdown if behind) |
| Intake API, reporter fingerprint, cases, actions | routers/intake.py, reporters.py, cases.py | – | TODO (M4) |
| Mock portals + Institution Finder + OTP + token | portal_rb/app.py, portal_pgrc/app.py | shared/institution-finder.js/.css | TODO (M5) (placeholder pages exist) |
| Matching A/B/C + overlap alert | routers/matching.py, alerts.py, corroboration.py | pages/Overlaps.jsx, Alerts.jsx | TODO (M6) |
| Officer confirm/reject, audit, priority | routers/audit.py | pages/CaseDetail.jsx | TODO (M7) |
| Dashboard KPIs, cases list, search/filters, case detail, institution profile, needs review | routers/dashboard.py, search.py | pages/Dashboard, Cases, CaseDetail, InstitutionProfile, NeedsReview | TODO (M8) |
| Conflict rules + lead-bureau suggestion | routers/conflicts.py | – | TODO (M9) |
| Starvation / SLA alerts | routers/starvation.py | – | TODO (M10) |
| Reports + CSV export, Insights panel | routers/reports.py | pages/Reports.jsx, Insights.jsx | TODO (M11) |
| Embeddings upgrade (fastembed) | services/matching.py | – | TODO (M12, optional) |
| n8n endpoints + reset_demo.py | – | reset_demo.py | TODO (M13, optional) |
| Case graph view | routers/graph.py | pages/GraphView.jsx | STUB |
| Attention Index | routers/attention_index.py | pages/AttentionIndex.jsx | STUB |
| Email / SMS notifications | routers/notifications.py | – | STUB |
| Supporting-document storage | routers/documents.py | – | STUB |
| Local-LLM summaries | routers/llm_summary.py | – | STUB |
