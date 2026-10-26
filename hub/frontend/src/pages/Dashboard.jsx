// Dashboard: KPI tiles, what needs an officer's decision, bureau workload, institution-wise status, categories.
import { Link } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Loading, Panel, Tile, useGet } from "../components/ui.jsx";

const STATUS_COLUMNS = [["pending", "Pending"], ["under_process", "Under Process"], ["disposed", "Disposed"], ["transferred", "Transferred"], ["escalated", "Escalated"]];

export default function Dashboard() {
  const kpi = useGet("/api/dashboard/kpis");
  const top = useGet("/api/cases?sort=priority&page_size=5");
  const late = useGet("/api/starvation?limit=5");
  if (!kpi.data) return <Loading state={kpi} />;
  const { totals: t, suggestions_waiting: w } = kpi.data;
  const bureauChart = kpi.data.by_bureau.map((b) => ({ bureau: b.assigned_bureau, Pending: b.by_status.pending, "Under Process": b.by_status.under_process, Escalated: b.by_status.escalated, Overdue: b.overdue }));

  return (
    <div className="space-y-6">
      <RoleBanner />
      <div className="flex items-end justify-between">
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <span className="text-xs text-slate-500">Live from the hub · as of {kpi.data.as_of}</span>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
        <Tile label="Total cases" value={t.total} to="/cases" />
        <Tile label="Pending" value={t.pending} tone="amber" to="/cases?status=Pending" />
        <Tile label="Under process" value={t.under_process} tone="blue" to="/cases?status=Under Process" />
        <Tile label="Disposed" value={t.disposed} tone="green" to="/cases?status=Disposed" />
        <Tile label="Transferred" value={t.transferred} tone="purple" to="/cases?status=Transferred" />
        <Tile label="Escalated" value={t.escalated} tone="red" to="/cases?status=Escalated" />
        <Tile label="Beyond timeline" value={t.overdue} tone="red" to="/cases?overdue=true" hint="open past expected date" />
        <Tile label="Needs review" value={t.unverified} to="/needs-review" hint="college not identified" />
      </div>

      <Panel title="Waiting for an officer's decision" right={<Link className="text-sm text-blue-700 hover:underline" to="/overlaps">Open overlaps</Link>}>
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Mini label="Potential overlapping cases" value={w.cross_bureau} />
          <Mini label="Conflicting actions" value={w.conflict} tone="red" />
          <Mini label="Duplicate actions" value={w.duplicate_action} />
          <Mini label="Possible duplicates (same reporter)" value={w.same_reporter} />
          <Mini label="Corroboration suggestions" value={w.corroboration} />
          <Mini label="Open alerts" value={kpi.data.open_alerts} to="/alerts" />
        </div>
        <p className="mt-3 text-xs text-slate-500">The system only suggests. Nothing is linked and no priority boost is applied until an officer confirms.</p>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Bureau-wise workload">
          <div className="h-64">
            <ResponsiveContainer>
              <BarChart data={bureauChart}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="bureau" /><YAxis allowDecimals={false} /><Tooltip /><Legend />
                <Bar dataKey="Pending" stackId="a" fill="#f59e0b" />
                <Bar dataKey="Under Process" stackId="a" fill="#3b82f6" />
                <Bar dataKey="Escalated" stackId="a" fill="#ef4444" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <table className="mt-3 w-full text-sm">
            <thead><tr className="text-left text-xs text-slate-500"><th>Bureau</th><th>Total</th><th>Open</th><th>Beyond timeline</th></tr></thead>
            <tbody>{kpi.data.by_bureau.map((b) => (
              <tr key={b.assigned_bureau} className="border-t"><td className="py-1 font-medium">{b.assigned_bureau}</td><td>{b.total}</td><td>{b.open}</td><td className="text-red-700">{b.overdue}</td></tr>
            ))}</tbody>
          </table>
        </Panel>

        <Panel title="Cases by category">
          <div className="h-80">
            <ResponsiveContainer>
              <BarChart data={kpi.data.by_category} layout="vertical" margin={{ left: 60 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" allowDecimals={false} /><YAxis type="category" dataKey="category" width={170} tick={{ fontSize: 11 }} /><Tooltip />
                <Bar dataKey="total" fill="#475569" name="Cases" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <Panel title="Institution-wise status (most open cases first)">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-slate-500">
              <th>Institution</th>{STATUS_COLUMNS.map(([, l]) => <th key={l}>{l}</th>)}<th>Beyond timeline</th>
            </tr></thead>
            <tbody>{kpi.data.by_institution.map((i) => (
              <tr key={i.institution_id} className="border-t">
                <td className="py-1"><Link className="text-blue-700 hover:underline" to={"/institutions/" + i.institution_id}>{i.name}</Link> <span className="text-xs text-slate-400">{i.institution_id}</span></td>
                {STATUS_COLUMNS.map(([k]) => <td key={k}>{i.by_status[k]}</td>)}
                <td className="text-red-700">{i.overdue}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </Panel>

      {late.data && (
        <Panel title="Stalled and deadline watch" right={<Link className="text-sm text-blue-700 hover:underline" to="/alerts">All alerts</Link>}>
          <div className="grid gap-4 lg:grid-cols-3">
            <Watch title="Stalled (no action)" total={late.data.counts.stalled} rows={late.data.stalled}
              detail={(c) => `${c.idle_days} days without action`} />
            <Watch title="Due soon" total={late.data.counts.due_soon} rows={late.data.due_soon}
              detail={(c) => `due ${c.expected_disposal_date} (${c.days_to_due} day(s) left)`} />
            <Watch title="Consider escalating" total={late.data.counts.escalation_suggested} rows={late.data.escalation_suggested}
              detail={(c) => `${c.days_overdue} days past expected date`} />
          </div>
          <p className="mt-3 text-xs text-slate-500">
            Limits (configurable): stalled after {late.data.thresholds.STARVATION_DAYS} days without action, due soon within {late.data.thresholds.SLA_DUE_SOON_DAYS} days,
            escalation suggested {late.data.thresholds.ESCALATION_OVERDUE_DAYS} days past the expected date. Escalating is always the officer's decision.
          </p>
        </Panel>
      )}

      <Panel title="Highest priority cases" right={<Link className="text-sm text-blue-700 hover:underline" to="/cases">All cases</Link>}>
        {top.data && (
          <ul className="divide-y text-sm">
            {top.data.items.map((c) => (
              <li key={c.hub_case_id} className="flex items-center justify-between gap-3 py-2">
                <span><Link className="font-medium text-blue-700 hover:underline" to={"/cases/" + c.hub_case_id}>{c.source_case_no}</Link> · {c.institution_name || "College not identified"} · {c.title}</span>
                <span className="shrink-0 text-slate-500">priority {c.priority_score}</span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

function Mini({ label, value, to, tone }) {
  const body = <div className="rounded-lg border p-3"><div className={"text-2xl font-semibold " + (tone === "red" && value > 0 ? "text-red-700" : "")}>{value}</div><div className="text-xs text-slate-500">{label}</div></div>;
  return to ? <Link to={to}>{body}</Link> : body;
}

function Watch({ title, total, rows, detail }) {
  return (
    <div className="rounded-lg border p-3">
      <div className="flex items-baseline justify-between"><span className="font-medium">{title}</span><span className="text-2xl font-semibold">{total}</span></div>
      <ul className="mt-2 space-y-1 text-sm">
        {rows.map((c) => (
          <li key={c.hub_case_id}>
            <Link className="font-medium text-blue-700 hover:underline" to={"/cases/" + c.hub_case_id}>{c.source_case_no}</Link>{" "}
            <span className="text-slate-500">{c.bureau} · {detail(c)}</span>
          </li>
        ))}
        {rows.length === 0 && <li className="text-slate-500">None</li>}
      </ul>
      {total > rows.length && <Link className="mt-2 block text-xs text-blue-700 hover:underline" to="/alerts">and {total - rows.length} more in Alerts</Link>}
    </div>
  );
}

// One line under the header telling this role what it can do here (read from the hub's permissions).
const ROLE_HELP = {
  rb_officer: "Work the RB cases, log actions, confirm or reject suggested links, transfer or escalate.",
  pgrc_officer: "Work the PGRC cases, log actions, confirm or reject suggested links, transfer or escalate.",
  other_bureau: "See the cases assigned to your bureau and the overlaps at those colleges. Log actions on your cases.",
  regional_office: "See your region only. Add remarks and escalate.",
  senior_management: "Read-only view of everything: KPIs, ageing, Insights, reports and export, audit trail.",
  competent_authority: "Everything, plus escalations and open conflicts. You make the final call on the lead bureau.",
};
function RoleBanner() {
  const { user } = useAuth();
  const text = ROLE_HELP[user.role];
  return text ? <div id="role-banner" className="rounded-lg bg-blue-50 px-4 py-2 text-sm text-blue-900"><b>{user.role_label}:</b> {text}</div> : null;
}
