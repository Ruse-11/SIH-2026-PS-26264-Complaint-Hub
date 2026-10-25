// Cases list: search (institution name, AICTE ID, case ID), filters, sorting and paging. Filters live in the URL,
// so dashboard tiles can link straight to "?status=Pending" and the back button works.
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Loading, Panel, StatusBadge, fmtDate, useGet } from "../components/ui.jsx";

const PAGE_SIZE = 25;
const FIELDS = ["q", "bureau", "region", "category", "status", "date_from", "date_to", "overdue", "sort"];

export default function Cases() {
  const [params, setParams] = useSearchParams();
  const get = (k) => params.get(k) || "";
  const [q, setQ] = useState(get("q"));
  useEffect(() => setQ(get("q")), [params.get("q")]); // eslint-disable-line react-hooks/exhaustive-deps
  const page = Number(get("page") || 1);

  const query = new URLSearchParams();
  FIELDS.forEach((k) => get(k) && query.set(k, get(k)));
  if (get("institution_id")) query.set("institution_id", get("institution_id"));
  query.set("page", page);
  query.set("page_size", PAGE_SIZE);
  const list = useGet("/api/cases?" + query);
  const options = useGet("/api/cases/filters");

  function set(k, v) {
    const next = new URLSearchParams(params);
    v ? next.set(k, v) : next.delete(k);
    if (k !== "page") next.delete("page");
    setParams(next);
  }
  const o = options.data || { bureaus: [], regions: [], categories: [], statuses: [] };
  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Cases</h1>
      <Panel title="Search and filter">
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); set("q", q.trim()); }}>
          <input id="case-search" className="flex-1 rounded border px-3 py-2" value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Institution name, AICTE ID (SYN-0009) or case ID (RB-2026-0003, HUB-0005)" />
          <button className="rounded bg-slate-900 px-4 py-2 text-white">Search</button>
        </form>
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
          {get("institution_id") && <span className="rounded bg-slate-200 px-2 py-1">College {get("institution_id")} <button onClick={() => set("institution_id", "")}>×</button></span>}
          <button className="text-blue-700 hover:underline" onClick={() => { setQ(""); setParams({}); }}>Clear all</button>
        </div>
      </Panel>

      <Loading state={list} />
      {list.data && (
        <Panel title={list.data.total + " case" + (list.data.total === 1 ? "" : "s")}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs text-slate-500">
                <th>Case</th><th>Institution</th><th>Category</th><th>Status</th><th>Bureau / officer</th><th>Received</th><th>Last action</th><th>Priority</th>
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
