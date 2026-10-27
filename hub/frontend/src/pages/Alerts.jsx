// Alerts raised by the hub. Two kinds: "needs a decision" (overlaps, conflicts, duplicates) and "time watch" (stalled, overdue...).
// Acknowledge = "seen". Counts and filters are worked out in the browser from one list.
import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { LiveStamp, Loading, send, useGet } from "../components/ui.jsx";

// Plain-language name, group and what the officer should do.
const KIND = {
  OVERLAP: ["Overlapping cases", "decision", "Two bureaus have open cases at this college. Review and confirm or reject the link."],
  CONFLICT: ["Conflicting actions", "decision", "One bureau enforced and another closed. Decide who leads."],
  DUPLICATE_ACTION: ["Duplicate action", "decision", "Two bureaus did the same thing. Coordinate."],
  DUPLICATE: ["Duplicate complaint", "decision", "Same reporter filed twice. Confirm or reject."],
  CORROBORATION: ["Corroboration", "decision", "Independent reporters describe the same problem. Confirm or reject."],
  STALLED: ["Stalled", "time", "No action for a long time. Take the next step."],
  OVERDUE: ["Past deadline", "time", "The disposal deadline has passed."],
  DUE_SOON: ["Due soon", "time", "The deadline is close."],
  ESCALATION_SUGGESTED: ["Consider escalating", "time", "Far past the deadline. Escalating is your call."],
  PENDING_REMINDER: ["Not started", "time", "Nobody has started this case yet."],
  ESCALATED: ["Escalated", "info", "Sent to the Competent Authority."],
};
const GROUPS = [["decision", "Needs a decision"], ["time", "Time watch"], ["info", "For information"]];
const BAR = { critical: "border-l-red-600", warning: "border-l-amber-500", info: "border-l-blue-500" };
const SEV = { critical: "Critical", warning: "Warning", info: "Info" };

export default function Alerts() {
  const { api } = useAuth();
  const [group, setGroup] = useState("");
  const [type, setType] = useState("");
  const [openOnly, setOpenOnly] = useState(true);
  const [shown, setShown] = useState(25);
  const state = useGet(`/api/alerts?open_only=${openOnly}`, { every: 60 });
  const all = state.data || [];
  const kind = (t) => KIND[t] || [t, "info", ""];
  const groupCount = (g) => all.filter((a) => kind(a.type)[1] === g).length;
  const inGroup = all.filter((a) => !group || kind(a.type)[1] === group);
  const types = Object.keys(KIND).filter((t) => inGroup.some((a) => a.type === t));
  const list = inGroup.filter((a) => !type || a.type === type);

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <h1 className="text-xl font-semibold">Alerts</h1>
        <LiveStamp state={state} />
      </div>
      <p className="text-sm text-slate-600">What the hub noticed. <b>Needs a decision</b> alerts are suggestions waiting for an officer. <b>Time watch</b> alerts are deadlines and stalled cases. Most serious first.</p>

      <div className="grid gap-3 sm:grid-cols-3">
        {GROUPS.map(([g, label]) => (
          <button key={g} onClick={() => { setGroup(group === g ? "" : g); setType(""); setShown(25); }}
            className={"rounded border border-l-4 bg-white p-4 text-left hover:bg-slate-50 " + (group === g ? "border-blue-900 ring-2 ring-blue-200" : "border-l-slate-400")}>
            <div className="text-3xl font-semibold text-slate-900">{groupCount(g)}</div>
            <div className="text-sm text-slate-600">{label}</div>
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <button onClick={() => setType("")} className={"rounded-full px-3 py-1 " + (!type ? "bg-slate-900 text-white" : "bg-white hover:bg-slate-200")}>All ({inGroup.length})</button>
        {types.map((t) => (
          <button key={t} onClick={() => { setType(t); setShown(25); }} className={"rounded-full px-3 py-1 " + (type === t ? "bg-slate-900 text-white" : "bg-white hover:bg-slate-200")}>
            {kind(t)[0]} ({inGroup.filter((a) => a.type === t).length})
          </button>
        ))}
        <label className="ml-auto flex items-center gap-2"><input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} /> Hide acknowledged</label>
      </div>

      <Loading state={state} />
      {state.data && list.length === 0 && <div className="rounded bg-white p-6 text-slate-500">No alerts here.</div>}
      <ul className="space-y-2">
        {list.slice(0, shown).map((a) => {
          const [label, , todo] = kind(a.type);
          return (
            <li key={a.id} className={"flex flex-wrap items-start justify-between gap-3 rounded border border-l-4 bg-white p-4 " + (BAR[a.severity] || "border-l-slate-400")}>
              <div className="max-w-3xl">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="font-semibold uppercase tracking-wide text-slate-700">{label}</span>
                  <span className="text-slate-400">·</span><span className="text-slate-500">{SEV[a.severity] || a.severity}</span>
                  <span className="text-slate-400">·</span><span className="text-slate-500">{a.created_at.slice(0, 10)}</span>
                </div>
                {a.institution && <div className="mt-1 font-medium text-slate-900">{a.institution.official_name}</div>}
                <p className="mt-1 text-sm text-slate-700">{a.message}</p>
                {todo && <p className="mt-1 text-xs text-slate-500">What to do: {todo}</p>}
                <div className="mt-2 flex gap-3 text-sm">
                  {a.link_id && <Link className="text-blue-700 hover:underline" to={"/overlaps?link=" + a.link_id}>Review suggestion →</Link>}
                  {a.case_id && <Link className="text-blue-700 hover:underline" to={"/cases/" + a.case_id}>Open case {a.source_case_no} →</Link>}
                </div>
              </div>
              {a.acknowledged_by ? <span className="text-xs text-slate-500">Seen by {a.acknowledged_by}</span>
                : <button className="rounded border px-3 py-1 text-sm hover:bg-slate-100" onClick={() => send(api, `/api/alerts/${a.id}/acknowledge`).then(state.reload)}>Mark as seen</button>}
            </li>
          );
        })}
      </ul>
      {list.length > shown && (
        <button className="rounded border bg-white px-4 py-2 text-sm hover:bg-slate-100" onClick={() => setShown(shown + 25)}>
          Show more ({list.length - shown} left)
        </button>
      )}
    </div>
  );
}
