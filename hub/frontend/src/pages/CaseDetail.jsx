// One case: details, priority breakdown, chronological action history, linked cases (with confirm / reject).
import { Link, useParams } from "react-router-dom";
import LinkCard from "../components/LinkCard.jsx";
import { Loading, Panel, StatusBadge, fmtDate, useGet } from "../components/ui.jsx";

const STANCE = { ENFORCING: "bg-red-100 text-red-800", REQUESTING: "bg-amber-100 text-amber-800", CLOSING: "bg-green-100 text-green-800", NEUTRAL: "bg-slate-100 text-slate-700" };

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

      <Panel title={"Linked and suggested cases (" + d.links.length + ")"}>
        {d.links.length === 0 && <p className="text-sm text-slate-500">No overlaps or duplicates suggested for this case.</p>}
        <div className="space-y-3">{d.links.map((l) => <LinkCard key={l.id} link={l} onChanged={c.reload} />)}</div>
      </Panel>
    </div>
  );
}
