// Institution profile: details, complaint history (oldest first), overlap suggestions and alerts for one college.
import { Link, useParams } from "react-router-dom";
import LinkCard from "../components/LinkCard.jsx";
import { Loading, Panel, StatusBadge, fmtDate, useGet } from "../components/ui.jsx";

export default function InstitutionProfile() {
  const { id } = useParams();
  const h = useGet(`/api/institutions/${id}/history`);
  if (!h.data) return <Loading state={h} />;
  const d = h.data;
  return (
    <div className="space-y-6">
      <div>
        <Link to="/" className="text-sm text-blue-700 hover:underline">← Dashboard</Link>
        <h1 className="mt-1 text-xl font-semibold">{d.official_name} <span className="text-sm font-normal text-slate-400">{d.aicte_id}</span></h1>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Institution">
          <dl className="grid grid-cols-[8rem_1fr] gap-y-1 text-sm">
            <dt className="text-slate-500">Address</dt><dd>{d.address_line}, {d.area}, {d.district}, {d.state}</dd>
            <dt className="text-slate-500">Region</dt><dd>{d.region}</dd>
            <dt className="text-slate-500">Type</dt><dd>{d.type}</dd>
            <dt className="text-slate-500">Programs</dt><dd>{d.programs}</dd>
            <dt className="text-slate-500">Established</dt><dd>{d.established_year}</dd>
            {d.parent_name && <><dt className="text-slate-500">Parent</dt><dd>{d.parent_name}</dd></>}
          </dl>
        </Panel>
        <Panel title="Complaint history (what you may see)">
          <p className="text-sm">{d.cases.length} case(s). <Link className="text-blue-700 hover:underline" to={"/cases?institution_id=" + d.aicte_id}>Open in case list</Link></p>
        </Panel>
      </div>

      <Panel title="Complaint history, oldest first">
        {d.cases.length === 0 && <p className="text-sm text-slate-500">No complaints on record for this college.</p>}
        <ol className="space-y-2 border-l pl-4 text-sm">
          {d.cases.map((c) => (
            <li key={c.hub_case_id}>
              <span className="text-xs text-slate-500">{fmtDate(c.received_at)}</span>{" "}
              <Link className="font-medium text-blue-700 hover:underline" to={"/cases/" + c.hub_case_id}>{c.source_case_no}</Link>{" "}
              <StatusBadge status={c.status} /> · {c.assigned_bureau} · {c.category} · {c.title}
              <div className="text-xs text-slate-500">Last action: {c.last_action || "–"} ({fmtDate(c.last_action_at)})</div>
            </li>
          ))}
        </ol>
      </Panel>

      <Panel title={"Overlap and duplicate suggestions (" + d.links.length + ")"}>
        <div className="space-y-3">{d.links.map((l) => <LinkCard key={l.id} link={l} onChanged={h.reload} />)}</div>
        {d.links.length === 0 && <p className="text-sm text-slate-500">None.</p>}
      </Panel>
    </div>
  );
}
