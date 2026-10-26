// Cases list: search (institution name, AICTE ID, case ID), filters, sorting and paging. Filters live in the URL,
// so dashboard tiles can link straight to "?status=Pending" and the back button works.
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import InstitutionSuggest from "../components/InstitutionSuggest.jsx";
import { LiveStamp, Loading, Panel, StatusBadge, fmtDate, useGet, useToast } from "../components/ui.jsx";

const PAGE_SIZE = 25;
const FIELDS = ["q", "bureau", "region", "category", "status", "date_from", "date_to", "overdue", "sort"];

export default function Cases() {
  const [params, setParams] = useSearchParams();
  const get = (k) => params.get(k) || "";
  const [q, setQ] = useState(get("q"));
  useEffect(() => setQ(get("q")), [params.get("q")]); // eslint-disable-line react-hooks/exhaustive-deps
  const page = Number(get("page") || 1);
  const { api, user } = useAuth();
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  // Download every case matching the current search and filters (not just this page) as CSV.
  async function downloadCaseFile() {
    setBusy(true);
    try {
      const ex = new URLSearchParams();
      FIELDS.forEach((k) => get(k) && ex.set(k, get(k)));
      if (get("institution_id")) ex.set("institution_id", get("institution_id"));
      const r = await api("/api/cases/export?" + ex);
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "Export failed");
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url; a.download = "case_file.csv"; a.click();
      URL.revokeObjectURL(url);
      toast({ title: "Case file downloaded", lines: ["It holds every case matching your filters. The export is recorded in the audit trail."] });
    } catch (e) {
      toast({ title: "Could not download", lines: [e.message], tone: "error" });
    } finally { setBusy(false); }
  }

  const query = new URLSearchParams();
  FIELDS.forEach((k) => get(k) && query.set(k, get(k)));
  if (get("institution_id")) query.set("institution_id", get("institution_id"));
  query.set("page", page);
  query.set("page_size", PAGE_SIZE);
  const list = useGet("/api/cases?" + query, { every: 60 });
  const options = useGet("/api/cases/filters");
  const picked = useGet(get("institution_id") ? "/api/institutions/" + get("institution_id") : null);

  function set(k, v) {
    const next = new URLSearchParams(params);
    v ? next.set(k, v) : next.delete(k);
    if (k !== "page") next.delete("page");
    setParams(next);
  }
  // a typed search replaces a picked college (otherwise the two filters would silently combine)
  function search(text) {
    const next = new URLSearchParams(params);
    text ? next.set("q", text) : next.delete("q");
    next.delete("institution_id");
    next.delete("page");
    setParams(next);
  }
  const o = options.data || { bureaus: [], regions: [], categories: [], statuses: [] };
  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1;

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between"><h1 className="text-xl font-semibold">Cases</h1><LiveStamp state={list} /></div>
      <Panel title="Search and filter">
        <div className="flex gap-2">
          <InstitutionSuggest id="case-search" className="flex-1" value={q} onChange={setQ}
            placeholder="Type a college name (suggestions appear), an AICTE ID (SYN-0009) or a case ID (RB-2026-0003)"
            onPick={(c) => { const next = new URLSearchParams(params); next.set("institution_id", c.aicte_id); next.delete("q"); next.delete("page"); setQ(""); setParams(next); }}
            onSubmit={search} />
          <button className="rounded bg-slate-900 px-4 py-2 text-white" onClick={() => search(q.trim())}>Search</button>
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Select label="Bureau" value={get("bureau")} options={o.bureaus} onChange={(v) => set("bureau", v)} />
          <Select label="Region" value={get("region")} options={o.regions} onChange={(v) => set("region", v)} />
          <Select label="Category" value={get("category")} options={o.categories} onChange={(v) => set("category", v)} />
          <Select label="Status" value={get("status")} options={o.statuses} onChange={(v) => set("status", v)} />
          <DateField label="Received from" value={get("date_from")} onChange={(v) => set("date_from", v)} />
          <DateField label="Received to" value={get("date_to")} onChange={(v) => set("date_to", v)} />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-4 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" checked={get("overdue") === "true"} onChange={(e) => set("overdue", e.target.checked ? "true" : "")} /> Only beyond timeline</label>
          <label className="flex items-center gap-2">Sort by
            <select className="rounded border px-2 py-1" value={get("sort") || "priority"} onChange={(e) => set("sort", e.target.value)}>
              <option value="priority">Highest priority</option><option value="received">Newest</option><option value="oldest">Oldest</option><option value="last_action">Last action</option>
            </select></label>
          {get("institution_id") && <span className="rounded bg-slate-200 px-2 py-1">College: {(picked.data && picked.data.official_name) || get("institution_id")}{picked.data && picked.data.children && picked.data.children.length > 0 ? " (and its colleges)" : ""} <button onClick={() => set("institution_id", "")}>×</button></span>}
          <button className="text-blue-700 hover:underline" onClick={() => { setQ(""); setParams({}); }}>Clear all</button>
        </div>
      </Panel>

      <Loading state={list} />
      {list.data && (
        <Panel title={list.data.total + " case" + (list.data.total === 1 ? "" : "s")}
          right={user.permissions.can_export
            ? <button id="download-case-file" disabled={busy || list.data.total === 0} onClick={downloadCaseFile}
                className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-40">{busy ? "Preparing…" : "Download case file (CSV)"}</button>
            : <span className="text-xs text-slate-500">Your role cannot export.</span>}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs text-slate-500">
                <th>Case</th><th>Institution</th><th>Category</th><th>Status</th><th>Bureau / officer</th><th>Received</th><th>Last action</th><th>Next action</th><th>Priority</th>
              </tr></thead>
              <tbody>{list.data.items.map((c) => (
                <tr key={c.hub_case_id} className="border-t align-top">
                  <td className="py-2"><Link className="font-medium text-blue-700 hover:underline" to={"/cases/" + c.hub_case_id}>{c.source_case_no}</Link>
                    <div className="text-xs text-slate-400">{c.hub_case_id}</div></td>
                  <td>{c.institution_name || <em className="text-slate-500">not identified</em>}<div className="text-xs text-slate-400">{c.institution_id}</div></td>
                  <td>{c.category}</td>
                  <td><StatusBadge status={c.status} />{c.overdue && <div className="mt-1 text-xs font-medium text-red-700">beyond timeline</div>}</td>
                  <td>{c.assigned_bureau}<div className="text-xs text-slate-400">{c.assigned_officer}</div></td>
                  <td>{fmtDate(c.received_at)}</td>
                  <td>{c.last_action || "–"}<div className="text-xs text-slate-400">{fmtDate(c.last_action_at)}</div></td>
                  <td>{c.next_action || <span className="text-slate-400">–</span>}
                    {c.next_action && <div className={"text-xs " + (c.next_action_overdue ? "font-medium text-red-700" : "text-slate-400")}>due {fmtDate(c.next_action_due)}{c.next_action_overdue ? " (overdue)" : ""}</div>}</td>
                  <td>{c.priority_score}{c.suggestions_waiting > 0 && <div className="text-xs text-amber-700">{c.suggestions_waiting} suggestion(s)</div>}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <div className="mt-3 flex items-center justify-between text-sm">
            <button disabled={page <= 1} onClick={() => set("page", String(page - 1))} className="rounded border px-3 py-1 disabled:opacity-40">Previous</button>
            <span>Page {page} of {pages}</span>
            <button disabled={page >= pages} onClick={() => set("page", String(page + 1))} className="rounded border px-3 py-1 disabled:opacity-40">Next</button>
          </div>
        </Panel>
      )}
    </div>
  );
}

function Select({ label, value, options, onChange }) {
  return (
    <label className="text-xs text-slate-500">{label}
      <select className="mt-1 block w-full rounded border px-2 py-2 text-sm text-slate-900" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">All</option>{options.map((x) => <option key={x} value={x}>{x}</option>)}
      </select>
    </label>
  );
}
function DateField({ label, value, onChange }) {
  return (
    <label className="text-xs text-slate-500">{label}
      <input type="date" className="mt-1 block w-full rounded border px-2 py-2 text-sm text-slate-900" value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}
