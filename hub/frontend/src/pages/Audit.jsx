// Audit trail (M7 API): who did what, newest first. Senior management and competent authority only.
import { useState } from "react";
import { Loading, Panel, useGet } from "../components/ui.jsx";

export default function Audit() {
  const [action, setAction] = useState("");
  const state = useGet("/api/audit?limit=200" + (action ? "&action=" + encodeURIComponent(action) : ""));
  const rows = state.data || [];
  const kinds = [...new Set(rows.map((r) => r.action))].sort();
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Audit trail</h1>
      <Loading state={state} />
      <Panel title="Recent activity" right={
        <select className="rounded border px-2 py-1 text-sm" value={action} onChange={(e) => setAction(e.target.value)}>
          <option value="">All actions</option>
          {(action && !kinds.includes(action) ? [action] : []).concat(kinds).map((k) => <option key={k}>{k}</option>)}
        </select>}>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm" id="audit-table">
            <thead><tr className="border-b text-xs uppercase text-slate-500"><th className="px-2 py-2">When</th><th className="px-2">Who</th><th className="px-2">Action</th><th className="px-2">On</th><th className="px-2">Detail</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b last:border-0 align-top">
                  <td className="whitespace-nowrap px-2 py-2">{r.at.replace("T", " ")}</td>
                  <td className="px-2">{r.actor} <span className="text-xs text-slate-500">({r.role})</span></td>
                  <td className="px-2 font-medium">{r.action}</td>
                  <td className="px-2">{r.entity_type} {r.entity_id}</td>
                  <td className="px-2 text-xs text-slate-600">{r.detail ? JSON.stringify(r.detail) : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
