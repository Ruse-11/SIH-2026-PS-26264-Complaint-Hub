# PS 26264: requirement-by-requirement check, gaps, and pending features
Checked 26 Oct 2026 against the full problem statement text (`sih_ps_2026.txt`) and the code as built (M0 to M13).
Legend: DONE = works and tested. PARTIAL = works but a part of the wording is missing. GAP = not built.

## A. Objective (what officials must be able to do)
| PS requirement | Status | Where / note |
|---|---|---|
| View all cases in one place | DONE | Cases page, dashboard, search and filters |
| Identify the Bureau/Cell handling each case | DONE | Bureau and officer on every case, institution profile |
| Track complete status and movement | DONE | Action history, transfers and escalations are actions with from/to bureau |
| Identify RB and PGRC overlap, or multiple bureaus on one institution | DONE | Cross-bureau overlap (rule C), alert "Potential Overlapping Cases – Coordination Required" |
| Avoid duplication, ensure coordination | DONE | Duplicate-action and conflict rules, lead-bureau suggestion, officer confirm/reject |
| Monitor pending, disposed, under process, transferred, escalated | DONE | Dashboard KPIs |
| Institution-wise, region-wise, bureau-wise, status-wise reports | DONE | Reports page and CSV export |
| Alerts for pending cases and cases nearing timelines | DONE | Due soon, overdue, stalled, pending reminder, escalation |

## B. Key features
| # | Feature | Status | Note |
|---|---|---|---|
| 1 | Institution profile: AICTE ID, name, address, region, details, history | DONE | Institution profile page |
| 2 | Case tracking: ID, receipt date, category, status, bureau, officer, last action, date of last action, expected disposal | DONE | |
| 2 | **Next action required** | DONE | Optional "next step" and "due by" when logging an action; if blank the hub suggests one by rule (for example after a show-cause: wait for the reply). Shown on the case, the cases list, the CSV and the case file. |
| 3 | Automatic overlap detection, overlap alert | DONE | |
| 3 | **Enable linking/mapping of related cases** | **PARTIAL** | Officers can confirm or reject the system's suggestions. An officer cannot yet link two cases by hand that the system did not suggest. |
| 3 | "RB, PGRC or **other** Bureaus/Cells" | DONE | A third bureau, the Quality Assurance Cell (QAC), has 12 synthetic cases and the "Other bureau" login sees them. RB and PGRC officers can transfer cases to QAC; QAC can be chosen as lead bureau. |
| 4 | Real-time dashboard with all listed numbers | DONE | Numbers are computed live on every load. Alerts refresh every 30 minutes and after each action. The dashboard, alerts, overlaps and cases pages now also refresh by themselves every 60 seconds with an "Updated hh:mm:ss" label and a Refresh now button. |
| 5 | Chronological history, officer/bureau, timestamp, remarks | DONE | |
| 5 | **Supporting documents** | **PARTIAL** | A document reference can be typed per action. There is no upload or document list. |
| 5 | Transfer/escalation history | DONE | Shown in the action history |
| 6 | Search and filters (name, AICTE ID, case ID, bureau, region, category, status, date range) | DONE | Search engine understands initials, typos, partial words |
| 7 | Duplicate/overlap alerts, pending reminders, escalation alerts, timeline/SLA alerts | DONE | In-app alerts. The PS word "notifications" could also mean email/SMS, which is future scope. |
| 8 | Bureau, region, institution history, ageing, disposal rate, overlaps, monthly/quarterly reports | DONE | All 9 reports, CSV export |

## C. Innovation expected
| Requirement | Status | Note |
|---|---|---|
| Match complaints about the same institution even when descriptions or references differ | DONE | Institution ID is confirmed by the reporter; text similarity (TF-IDF, optional embeddings) finds related complaints |
| Show "Potential Overlapping Cases – Coordination Required" | DONE | Exact wording used |

## D. Expected outcome
Reduce duplication, prevent conflicting actions (conflict rule), improve coordination (lead-bureau suggestion), timely disposal (SLA alerts), accountability (audit trail, action history), real-time monitoring (live numbers), data-driven decisions (Insights, reports): all covered. The one soft spot is "real time" as a push update (see gap 6 below).

## E. Target users
RB, PGRC, other bureaus, regional offices, senior management, competent authority: one login and view for each. **Other bureaus have no data** (see gap 3).

## Update (26 Oct): gaps 1, 2, 3 and 6 below are now BUILT and tested (manual linking = "Link another case" on the case page). Gaps 4 and 5 remain.

## F. Gaps ranked (what I would do, in order)
| # | Gap | Why it matters to judges | Effort | Recommendation |
|---|---|---|---|---|
| 1 | **Next action required** field | It is a listed item under Case Tracking, so a judge reading the PS will look for it. | Small (about 1 hour) | **Build.** Optional "Next step" and "Due by" when logging an action, shown on the case and the cases list, with a rule-based default per action (for example after a show-cause: "Await the institution's reply"). |
| 2 | **Manual link** of two cases by an officer | PS: "Enable linking/mapping of related complaints". Today it is only confirm/reject. | Small to medium (1 to 2 hours) | **Build.** "Link another case" on the case page (same institution, pick the other case, choose a type and a note). It goes through the same confirm/audit path. |
| 3 | **Other bureaus have data** | PS names "other bureaus" in several places and the Other bureau user sees nothing. | Small (data and config) | **Build.** Seed a few cases for 1 or 2 extra bureaus (for example "Approval Bureau", "Quality Assurance Cell"), and allow transfers to them. Needs a small dataset addition from you or your dataset teammate, or I can generate it. |
| 4 | Supporting document upload/list | PS lists "supporting documents". | Medium | Build a simple version: attach a file name and a note, store the file in a local folder, list it on the case and in the case file. Real document storage stays future scope. |
| 5 | Email/SMS delivery of alerts | PS "alerts and notifications" | Medium, and needs external services | Keep as future scope. Say "in-app alerts today, the n8n/Telegram clip shows how delivery plugs in". |
| 6 | Page auto-refresh | "Real-time" wording | Small (30 minutes) | Cheap to add: the dashboard and alert pages re-fetch every 60 seconds with a "last updated" label. |
| 7 | Editing SLA and thresholds in the browser | "Prescribed timelines" are configurable but only in the database | Medium | Idea, not needed. |

## G. Pending (future-scope) features, as in your screenshot
| Feature | State | Note |
|---|---|---|
| Graph (case graph view) | Stub page "Coming soon", API returns 501 | Colleges, cases and links drawn as a network. Good visual for the PPT. |
| Attention (Institution Attention Index) | Stub | One score per college from repeats, overdue cases and conflicts, to rank "colleges to look at". |
| **Reporter verification with Aadhaar through DigiLocker** (instead of the mock OTP) | Stub added today (`/api/verification`, returns 501) | See below. |

### How Aadhaar/DigiLocker verification would replace the mock OTP
1. In the portal's step 2 the reporter would press "Verify with DigiLocker" instead of entering an OTP. The portal redirects to DigiLocker, where the reporter signs in and gives **consent**.
2. The portal receives a verified result from DigiLocker (through the government's API Setu). It never sees or stores the Aadhaar number. It keeps only a one-way hash of DigiLocker's reference for that person, the same way the mock OTP stores a hash of the phone number today.
3. The hub already works this way: it identifies a reporter only by a hashed fingerprint, so nothing in the hub changes. The same person verified on RB and PGRC still maps to one reporter, which keeps duplicate and corroboration detection correct.
4. What it adds: real people, harder to fake many reporters, which strengthens the "corroborated by N independent reporters" claim.
5. What it does not prove: that the complaint is true. Officers still decide.
6. Why it is not in the prototype: DigiLocker integration needs the organisation to be registered as a requester with the government (API Setu), real credentials and legal compliance (the Aadhaar Act restricts how Aadhaar data is handled). That cannot be done for a hackathon, so it stays "future scope" in the PPT. The seam is already clean: the portal's OTP request and verify calls are the only two places to swap.
7. Optional for the demo: a clearly labelled **mock DigiLocker button** in the portal that mimics the redirect and consent screen and returns the same kind of token, to show the idea. I have not built it. Say if you want it.

## H. What I suggest next
Build gaps 1, 2, 3 and 6 (about half a day together). They close the only places where the PS wording is not fully met. Then rehearse the demo. Gaps 4 and 5 stay as "future scope" or a small version if time allows.
