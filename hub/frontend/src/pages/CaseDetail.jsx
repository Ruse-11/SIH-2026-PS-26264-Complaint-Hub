// One case: details, priority breakdown, chronological action history, linked cases (with confirm / reject).
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import LinkCard from "../components/LinkCard.jsx";
import { Loading, Panel, StatusBadge, fmtDate, send, useGet, useToast } from "../components/ui.jsx";

const STANCE = { ENFORCING: "bg-red-100 text-red-800", REQUESTING: "bg-amber-100 text-amber-800", CLOSING: "bg-green-100 text-green-800", NEUTRAL: "bg-slate-100 text-slate-700" };

// Officers log what they did on the case. The hub then checks for conflicts or duplicate actions with the other bureau.
function LogAction({ caseData, onDone }) {
  const { api } = useAuth();
  const toast = useToast();
  const types = useGet("/api/cases/action-types");
  const [type, setType] = useState("");
  const [remarks, setRemarks] = useState("");
  const [doc, setDoc] = useState("");
  const [toBureau, setToBureau] = useState("");
  const [busy, setBusy] = useState(false);
  const closed = caseData.status === "Disposed" || caseData.status === "unverified_institution";
  if (!types.data || types.data.length === 0 || closed) return null;
  const other = caseData.assigned_bureau === "RB" ? "PGRC" : "RB";

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    try {
      const done = await send(api, `/api/cases/${caseData.hub_case_id}/actions`, {
        action_type: type, remarks, doc_ref: doc, to_bureau: type === "Transferred" ? toBureau || other : null });
      const lines = [`Status is now ${done.status}.`, ...done.alerts_created.map((a) => "⚠ " + a.message)];
      toast({ tone: done.alerts_created.length ? "error" : "success", title: `✓ Action logged: ${done.action_type}`, lines });
      setType(""); setRemarks(""); setDoc(""); setToBureau("");
      onDone();
    } catch (err) {
      toast({ tone: "error", title: "Could not log the action", lines: [err.message] });
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel title="Log an action">
      <form onSubmit={save} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <select id="action-type" required value={type} onChange={(e) => setType(e.target.value)} className="rounded border px-2 py-2 text-sm">
          <option value="">Choose action…</option>
          {["ENFORCING", "REQUESTING", "CLOSING", "NEUTRAL"].map((st) => (
            <optgroup key={st} label={st.charAt(0) + st.slice(1).toLowerCase()}>
              {types.data.filter((t) => t.stance === st).map((t) => <option key={t.action_type}>{t.action_type}</option>)}
            </optgroup>
          ))}
        </select>
        {type === "Transferred" && (
          <select value={toBureau || other} onChange={(e) => setToBureau(e.target.value)} className="rounded border px-2 py-2 text-sm">
            {["RB", "PGRC"].filter((b) => b !== caseData.assigned_bureau).map((b) => <option key={b} value={b}>Transfer to {b}</option>)}
          </select>
        )}
        <input id="action-remarks" value={remarks} maxLength={500} onChange={(e) => setRemarks(e.target.value)} placeholder="Remarks" className="rounded border px-3 py-2 text-sm lg:col-span-2" />
        <input value={doc} maxLength={200} onChange={(e) => setDoc(e.target.value)} placeholder="Document reference (optional)" className="rounded border px-3 py-2 text-sm" />
        <button disabled={busy || !type} className="rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-40">{busy ? "Saving…" : "Log action"}</button>
      </form>
      <p className="mt-2 text-xs text-slate-500">Closing actions dispose the case. Enforcing and requesting actions are checked against the other bureau's actions at this college.</p>
    </Panel>
  );
}

export default function CaseDetail() {
  const { id } = useParams();
  const c = useGet("/api/cases/" + id);
  if (!c.data) return <Loading state={c} />;
  const d = c.data;
  const p = d.priority;
  return (
    <div className="space-y-6">
      <div>
        <Link to="/cases" className="text-sm text-blue-700 hover:underline">← Cases</Link>
        <h1 className="mt-1 text-xl font-semibold">{d.source_case_no} <span className="text-sm font-normal text-slate-400">{d.hub_case_id}</span></h1>
        <p className="text-slate-700">{d.title}</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title="Details">
          <dl className="grid grid-cols-[8rem_1fr] gap-y-1 text-sm">
            <dt className="text-slate-500">Status</dt><dd><StatusBadge status={d.status} /></dd>
            <dt className="text-slate-500">Institution</dt>
            <dd>{d.institution ? <Link className="text-blue-700 hover:underline" to={"/institutions/" + d.institution.aicte_id}>{d.institution.official_name}</Link> : <em>not identified (needs review)</em>}
              {d.institution && <div className="text-xs text-slate-500">{d.institution.aicte_id} · {d.institution.district}, {d.institution.state}</div>}</dd>
            <dt className="text-slate-500">Category</dt><dd>{d.category}</dd>
            <dt className="text-slate-500">Bureau</dt><dd>{d.assigned_bureau} · {d.assigned_officer || "unassigned"}</dd>
            <dt className="text-slate-500">Received</dt><dd>{fmtDate(d.received_at)} via {d.source_system} portal</dd>
            <dt className="text-slate-500">Expected disposal</dt><dd>{fmtDate(d.expected_disposal_date)}</dd>
            <dt className="text-slate-500">Last action</dt><dd>{d.last_action || "–"} ({fmtDate(d.last_action_at)})</dd>
            <dt className="text-slate-500">College found by</dt><dd>{d.resolution_method}</dd>
            <dt className="text-slate-500">Reporter</dt><dd>{d.reporter_id} ({d.reporter_type})</dd>
          </dl>
          <p className="mt-3 rounded bg-slate-50 p-3 text-sm">{d.description}</p>
        </Panel>

        <Panel title={"Priority " + p.score}>
          <table className="w-full text-sm">
            <tbody>
              <tr><td>Severity {d.severity} × 10</td><td className="text-right">{p.parts.severity}</td></tr>
              <tr><td>Confirmed independent reporters ({p.confirmed_corroborators}) × 5</td><td className="text-right">{p.parts.corroboration}</td></tr>
              <tr><td>Age {p.age_days} days × 0.3 (max 60 days)</td><td className="text-right">{p.parts.age}</td></tr>
            </tbody>
          </table>
          {p.potential_boost > 0 && <p className="mt-3 rounded bg-amber-50 p-2 text-sm text-amber-900">Potential +{p.potential_boost} if an officer confirms the corroboration suggestion below.</p>}
          {d.cluster_id && <p className="mt-2 text-sm">Part of corroboration cluster #{d.cluster_id}.</p>}
        </Panel>

        <Panel title="Action history">
          <ol className="space-y-3 border-l pl-4 text-sm">
            {d.actions.map((a) => (
              <li key={a.seq}>
                <div className="font-medium">{a.action_type} <span className={"ml-1 rounded px-1.5 py-0.5 text-xs " + STANCE[a.stance]}>{a.stance.toLowerCase()}</span></div>
                <div className="text-xs text-slate-500">{fmtDate(a.at)} · {a.actor} · {a.bureau}{a.to_bureau ? " → " + a.to_bureau : ""}</div>
                {a.remarks && <div className="text-slate-700">{a.remarks}</div>}
                {a.doc_ref && <div className="text-xs text-slate-500">Document: {a.doc_ref}</div>}
              </li>
            ))}
            {d.actions.length === 0 && <li className="text-slate-500">No actions yet.</li>}
          </ol>
        </Panel>
      </div>

      <LogAction caseData={d} onDone={c.reload} />

      <Panel title={"Linked and suggested cases (" + d.links.length + ")"}>
        {d.links.length === 0 && <p className="text-sm text-slate-500">No overlaps or duplicates suggested for this case.</p>}
        <div className="space-y-3">{d.links.map((l) => <LinkCard key={l.id} link={l} onChanged={c.reload} />)}</div>
      </Panel>
    </div>
  );
}
