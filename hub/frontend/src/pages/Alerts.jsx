// Alerts raised by the hub (overlap, duplicate, corroboration). Acknowledge = "seen".
import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { Loading, send, useGet } from "../components/ui.jsx";

const TONE = { warning: "bg-amber-100 text-amber-800", critical: "bg-red-100 text-red-800", info: "bg-blue-100 text-blue-800" };

export default function Alerts() {
  const { api } = useAuth();
  const [type, setType] = useState("");
  const [openOnly, setOpenOnly] = useState(true);
  const alerts = useGet(`/api/alerts?open_only=${openOnly}${type ? "&type=" + type : ""}`);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Alerts</h1>
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <select className="rounded border bg-white px-2 py-1.5" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">All types</option><option value="OVERLAP">Overlap</option><option value="DUPLICATE">Duplicate</option><option value="CORROBORATION">Corroboration</option>
        </select>
        <label className="flex items-center gap-2"><input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} /> Not yet acknowledged</label>
      </div>
      <Loading state={alerts} />
      {alerts.data && alerts.data.length === 0 && <div className="rounded-xl bg-white p-6 text-slate-500">No alerts.</div>}
      <ul className="space-y-2">
        {(alerts.data || []).map((a) => (
          <li key={a.id} className="flex flex-wrap items-start justify-between gap-3 rounded-lg bg-white p-4 shadow-sm">
            <div className="max-w-3xl">
              <span className={"mr-2 rounded-full px-2 py-0.5 text-xs font-medium " + (TONE[a.severity] || "")}>{a.type}</span>
              <span className="text-xs text-slate-500">{a.created_at.replace("T", " ")} · {a.institution && a.institution.official_name}</span>
              <p className="mt-1 text-sm">{a.message}</p>
              <div className="mt-1 text-xs">
                {a.link_id && <Link className="text-blue-700 hover:underline" to={"/overlaps?link=" + a.link_id}>Review suggestion</Link>}
                {a.case_id && <> · <Link className="text-blue-700 hover:underline" to={"/cases/" + a.case_id}>{a.source_case_no}</Link></>}
              </div>
            </div>
            {a.acknowledged_by ? <span className="text-xs text-slate-500">Acknowledged by {a.acknowledged_by}</span>
              : <button className="rounded border px-3 py-1 text-sm hover:bg-slate-100" onClick={() => send(api, `/api/alerts/${a.id}/acknowledge`).then(alerts.reload)}>Acknowledge</button>}
          </li>
        ))}
      </ul>
    </div>
  );
}
