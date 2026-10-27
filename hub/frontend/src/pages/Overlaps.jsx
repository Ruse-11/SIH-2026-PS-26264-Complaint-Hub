// Overlaps: every suggestion that needs an officer. Cross-bureau overlaps are grouped by college so a heavy
// repeat college does not bury the rest. Confirm or reject right here.
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import LinkCard from "../components/LinkCard.jsx";
import { LINK_TYPE, LiveStamp, Loading, useGet } from "../components/ui.jsx";

const TABS = [["SUGGESTED", "Waiting for decision"], ["CONFIRMED", "Confirmed"], ["REJECTED", "Rejected"]];

export default function Overlaps() {
  const [params] = useSearchParams();
  const highlight = Number(params.get("link") || 0);
  const [status, setStatus] = useState("SUGGESTED");
  const [type, setType] = useState("");
  const state = useGet(`/api/matching/links?status=${status}`, { every: 60 });
  const all = state.data || [];
  const links = { ...state, data: state.data ? all.filter((l) => !type || l.link_type === type) : null };

  const groups = {};
  (links.data || []).forEach((l) => {
    const key = l.institution.aicte_id;
    (groups[key] = groups[key] || { name: l.institution.official_name, id: key, items: [] }).items.push(l);
  });
  const ordered = Object.values(groups).sort((a, b) => b.items.length - a.items.length);

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between"><h1 className="text-xl font-semibold">Overlaps, conflicts and duplicates</h1><LiveStamp state={links} /></div>
      <details className="rounded border bg-white p-3 text-sm text-slate-700" open={status === "SUGGESTED" && all.length > 0 && all.length < 4}>
        <summary className="cursor-pointer font-medium text-slate-900">What am I looking at?</summary>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          <li><b>Overlap:</b> two bureaus have open cases at the same college, so they should coordinate.</li>
          <li><b>Conflict:</b> one bureau took an enforcing action while another closed the case.</li>
          <li><b>Duplicate / same reporter:</b> the same person complained on both portals.</li>
          <li><b>Corroboration:</b> different reporters describe the same problem. Confirming it raises priority.</li>
        </ul>
        <p className="mt-2">The system only suggests. An officer confirms or rejects, and rejected pairs are never suggested again. Colleges with the most items are listed first.</p>
      </details>
      <div className="flex flex-wrap items-center gap-2">
        {TABS.map(([k, label]) => (
          <button key={k} onClick={() => { setStatus(k); setType(""); }} className={"rounded-full px-4 py-1.5 text-sm " + (status === k ? "bg-slate-900 text-white" : "bg-white hover:bg-slate-200")}>{label}</button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-slate-500">Show:</span>
        <button onClick={() => setType("")} className={"rounded-full border px-3 py-1 " + (!type ? "bg-blue-900 text-white" : "bg-white hover:bg-slate-100")}>All ({all.length})</button>
        {["CROSS_BUREAU", "CONFLICT", "DUPLICATE_ACTION", "SAME_REPORTER", "CORROBORATION", "RELATED"].filter((t) => all.some((l) => l.link_type === t)).map((t) => (
          <button key={t} onClick={() => setType(t)} className={"rounded-full border px-3 py-1 " + (type === t ? "bg-blue-900 text-white" : "bg-white hover:bg-slate-100")}>
            {LINK_TYPE[t]} ({all.filter((l) => l.link_type === t).length})
          </button>
        ))}
      </div>
      <Loading state={links} />
      {links.data && ordered.length === 0 && <div className="rounded-xl bg-white p-6 text-slate-500">Nothing here.</div>}
      {ordered.map((g, i) => (
        <details key={g.id} className="rounded-xl bg-white p-4 shadow-sm" open={i < 2 || g.items.some((l) => l.id === highlight)}>
          <summary className="cursor-pointer">
            <span className="font-semibold text-slate-900">{g.name}</span> <span className="text-xs text-slate-400">{g.id}</span>
            <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs">{g.items.length} item{g.items.length === 1 ? "" : "s"}</span>
            {Object.entries(g.items.reduce((m, l) => ({ ...m, [l.link_type]: (m[l.link_type] || 0) + 1 }), {})).map(([t, n]) => (
              <span key={t} className="ml-1 rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-900">{LINK_TYPE[t]} {n}</span>))}
          </summary>
          <div className="mt-3 space-y-3">
            {g.items.map((l) => <LinkCard key={l.id} link={l} highlight={l.id === highlight} onChanged={links.reload} />)}
          </div>
        </details>
      ))}
    </div>
  );
}
