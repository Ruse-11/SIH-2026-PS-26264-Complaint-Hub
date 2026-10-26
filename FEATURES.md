# FEATURES.md — feature → file → status

Status: **DONE** (works and tested) · **TODO (Mx)** (planned in that module, stub file exists) · **STUB** (future scope, file exists, returns 501 / "Coming soon").
Updated after every module.

| Feature | Backend file | Frontend / other file | Status |
|---|---|---|---|
| Project scaffold, run_all, health check | hub/backend/app/main.py, run_all.py | hub/frontend/src/App.jsx | DONE (M0) |
| Models + CSV seed loader | models.py, seed.py, services/institutions.py (normalizer), services/reporters.py (fingerprint) | data/*.csv | DONE (M1) |
| Institution registry, search, name resolver, guided filters, profile | routers/institutions.py, services/institutions.py | shared/institution-finder.js (UI in M5) | DONE (M2) |
| Login + roles (JWT, 6 seeded demo accounts, role permissions) | routers/auth.py, services/auth.py | pages/Login.jsx, src/auth.jsx, App.jsx header | DONE (M3) |
| Intake API (API key per portal), reporter fingerprint, case + first action, safe retry, audit row | routers/intake.py, services/intake.py, services/audit.py, services/reporters.py | – | DONE (M4) |
| Case detail with action history, case list, search, filters, Needs Review, assign college | routers/cases.py, services/cases.py, services/scope.py | pages/Cases, CaseDetail, NeedsReview | DONE (M8); bureau action sync `POST /api/actions` STUB |
| Mock portals (own DB, own case numbers, retry outbox), Institution Finder widget (search, confirm card + map, guided questions, not-listed), mock OTP, signed 30-min tokens | shared/portal_core.py, portal_rb/app.py, portal_pgrc/app.py | shared/institution-finder.js/.css, shared/portal-form.js, portal_*/static/index.html | DONE (M5) |
| Matching A/B/C + overlap alert | routers/matching.py, alerts.py, services/matching.py, similarity.py | pages/Overlaps.jsx, Alerts.jsx, components/LinkCard.jsx | DONE (M6 API, M8 screens) |
| Officer confirm/reject, audit, priority | routers/matching.py, audit.py, corroboration.py, services/decisions.py, priority.py | components/LinkCard.jsx, pages/CaseDetail.jsx | DONE (M7 API, M8 buttons); audit screen not built (API only) |
| Dashboard KPIs, global search, institution profile + history, role scoped views | routers/dashboard.py, search.py, institutions.py, services/dashboard.py | pages/Dashboard, InstitutionProfile, App.jsx header search | DONE (M8) |
| Conflict rules (enforcing vs closing), duplicate action, lead-bureau suggestion + competent authority decision, officers log actions (transfer, escalate, close) | routers/conflicts.py, cases.py, services/conflicts.py, actions.py, matching.py (suggest_lead) | components/LinkCard.jsx, pages/CaseDetail.jsx (Log an action), Overlaps.jsx | DONE (M9) |
| Starvation (stalled) and SLA alerts: due soon, overdue, pending reminder, escalation suggested, escalated; repeat-safe scan on start, every 30 min and after each action | routers/starvation.py, services/starvation.py, main.py | pages/Dashboard.jsx (watch panel), pages/Alerts.jsx | DONE (M10) |
| Reports (bureau, region, status, institution history, ageing, disposal rate, overlaps, monthly, quarterly) + CSV export (audited, formula-safe) | routers/reports.py, services/reports.py | pages/Reports.jsx | DONE (M11) |
| Insights panel (rule-based, each card shows its rule) | routers/reports.py (/insights), services/insights.py | pages/Insights.jsx | DONE (M11) |
| Case file download (CSV of the filtered Cases list, audited) | routers/cases.py (/export) | pages/Cases.jsx | DONE (M11) |
| Single-case file download (HTML report with summary, institution, reporter text, action history, linked cases, alerts, audit; print to PDF; audited) | services/casefile.py, routers/cases.py (/{id}/file) | pages/CaseDetail.jsx | DONE |
| Guided "Take action" panel (plain-language groups, effect preview, role-aware) and type/status filters on linked cases | services/actions.py | pages/CaseDetail.jsx | DONE |
| Audit trail screen + role banner on dashboard | routers/audit.py | pages/Audit.jsx, Dashboard.jsx | DONE (M11) |
| Shared institution search engine (initials like KIP, typos, partial words, places, AICTE IDs; prebuilt index; never-empty tiers; used by hub header, Cases search and both portals) | services/searchengine.py, routers/institutions.py (/search, /suggest), services/cases.py | shared/institution-finder.js, components/InstitutionSuggest.jsx | DONE |
| Embeddings upgrade (fastembed, off by default, TF-IDF fallback; `method` stored in each suggestion's reasons; shown in /api/health) | services/embeddings.py, services/similarity.py, services/matching.py | – | DONE (M12; real model untested in build sandbox, see PROGRESS) |
| reset_demo.py (one-command clean reset, dates shifted to today, portals cleared, demo-college check) and n8n replay support (call list + replay_check.py) | seed.py (shift_days), reset_demo.py | n8n/README.md, n8n/replay_check.py | DONE (M13); the n8n workflow itself is the teammate's |
| Case graph view | routers/graph.py | pages/GraphView.jsx | STUB |
| Attention Index | routers/attention_index.py | pages/AttentionIndex.jsx | STUB |
| Email / SMS notifications | routers/notifications.py | – | STUB |
| Supporting-document storage | routers/documents.py | – | STUB |
| Local-LLM summaries | routers/llm_summary.py | – | STUB |
