// Overlaps: every suggestion that needs an officer. Cross-bureau overlaps are grouped by college so a heavy
// repeat college does not bury the rest. Confirm or reject right here.
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import LinkCard from "../components/LinkCard.jsx";
import { LINK_TYPE, Loading, useGet } from "../components/ui.jsx";

const TABS = [["SUGGESTED", "Waiting for decision"], ["CONFIRMED", "Confirmed"], ["REJECTED", "Rejected"]];

export default function Overlaps() {
  const [params] = useSearchParams();
  const highlight = Number(params.get("link") || 0);
  const [status, setStatus] = useState("SUGGESTED");
  const [type, setType] = useState("");
  const links = useGet(`/api/matching/links?status=${status}${type ? "&link_type=" + type : ""}`);

  const groups = {};
  (links.data || []).forEach((l) => {
    const key = l.institution.aicte_id;
    (groups[key] = groups[key] || { name: l.institution.official_name, id: key, items: [] }).items.push(l);
  });
  const ordered = Object.values(groups).sort((a, b) => b.items.length - a.items.length);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Overlaps, conflicts and duplicates</h1>
      <p className="text-sm text-slate-600">The system suggests; the officer confirms or rejects. Confirmed corroboration raises priority, rejected pairs are never suggested again.</p>
      <div className="flex flex-wrap items-center gap-2">
        {TABS.map(([k, label]) => (
          <button key={k} onClick={() => setStatus(k)} className={"rounded-full px-4 py-1.5 text-sm " + (status === k ? "bg-slate-900 text-white" : "bg-white hover:bg-slate-200")}>{label}</button>
        ))}
        <select className="ml-auto rounded border bg-white px-2 py-1.5 text-sm" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">All types</option>
          {["CROSS_BUREAU", "CONFLICT", "DUPLICATE_ACTION", "SAME_REPORTER", "CORROBORATION", "RELATED"].map((t) => <option key={t} value={t}>{LINK_TYPE[t]}</option>)}
        </select>
      </div>
      <Loading state={links} />
      {links.data && ordered.length === 0 && <div className="rounded-xl bg-white p-6 text-slate-500">Nothing here.</div>}
      {ordered.map((g, i) => (
        <details key={g.id} className="rounded-xl bg-white p-4 shadow-sm" open={i < 3 || g.items.some((l) => l.id === highlight)}>
          <summary className="cursor-pointer font-medium">{g.name} <span className="text-xs text-slate-400">{g.id}</span> · {g.items.length} suggestion{g.items.length === 1 ? "" : "s"}</summary>
          <div className="mt-3 space-y-3">
            {g.items.map((l) => <LinkCard key={l.id} link={l} highlight={l.id === highlight} onChanged={links.reload} />)}
          </div>
        </details>
      ))}
    </div>
  );
}
