// One case: details, priority breakdown, chronological action history, linked cases (with confirm / reject).
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import LinkCard from "../components/LinkCard.jsx";
import { LINK_TYPE, Loading, Panel, StatusBadge, fmtDate, send, useGet, useToast } from "../components/ui.jsx";

const STANCE = { ENFORCING: "bg-red-100 text-red-800", REQUESTING: "bg-amber-100 text-amber-800", CLOSING: "bg-green-100 text-green-800", NEUTRAL: "bg-slate-100 text-slate-700" };

// What each action means, in plain words. The hub's action list (by role) decides which of these are offered.
const GROUPS = [
  { key: "update", title: "Update the case", help: "Record progress. A pending case moves to Under Process.",
    actions: { "Under Review": "The case is being looked at." } },
  { key: "ask", title: "Ask the institution", help: "Checked against what the other bureau has already asked this college.",
    actions: { "Documents Sought": "Ask the institution to send documents.", "Reply Sought from Institution": "Ask the institution to reply to the complaint." } },
  { key: "enforce", title: "Take enforcement action", help: "A strong step. The hub warns you if the other bureau has closed or already done the same at this college.",
    actions: { "Show-Cause Notice Issued": "Issue a show-cause notice to the institution.", "Inspection Ordered": "Order an inspection of the institution.", "Penalty Proposed": "Propose a penalty." } },
  { key: "close", title: "Close the case", help: "The case becomes Disposed. No further action can be logged on it.",
    actions: { "Closed - No Action": "No further step is needed.", "Disposed - Unsubstantiated": "The complaint is not supported by the facts.", "Disposed - Action Taken": "Action was taken and the case is complete." } },
  { key: "pass", title: "Pass it on", help: "Hand the case to someone else.",
    actions: { "Transferred": "Hand the case to the other bureau.", "Escalated to Competent Authority": "Send it to the Competent Authority for a decision." } },
];
const CLOSING = ["Closed - No Action", "Disposed - Unsubstantiated", "Disposed - Action Taken"];
const NEEDS_REMARKS = [...CLOSING, "Transferred", "Escalated to Competent Authority"];

// What will happen to the case if the officer saves this action.
function effectText(type, status, toBureau) {
  if (!type) return "";
  if (CLOSING.includes(type)) return "Result: status becomes Disposed (final).";
  if (type === "Transferred") return `Result: the case moves to ${toBureau} and its status becomes Transferred.`;
  if (type === "Escalated to Competent Authority") return "Result: status becomes Escalated and the competent authority is alerted.";
  return status === "Pending" ? "Result: status becomes Under Process." : `Result: status stays ${status}.`;
}

// Officers record what they did on the case. The hub then checks for conflicts or duplicate actions with the other bureau.
function LogAction({ caseData, onDone }) {
  const { api, user } = useAuth();
  const toast = useToast();
  const types = useGet("/api/cases/action-types");
  const [group, setGroup] = useState("");
  const [type, setType] = useState("");
  const [remarks, setRemarks] = useState("");
  const [doc, setDoc] = useState("");
  const [toBureau, setToBureau] = useState("");
  const [busy, setBusy] = useState(false);
  const closed = caseData.status === "Disposed" || caseData.status === "unverified_institution";
  if (!types.data) return null;
  if (types.data.length === 0) {
    return <Panel title="Take action on this case"><p className="text-sm text-slate-600">Your role ({user.role_label}) is read-only here. Bureau officers take actions on cases.</p></Panel>;
  }
  if (closed) {
    return <Panel title="Take action on this case"><p className="text-sm text-slate-600">
      {caseData.status === "Disposed" ? "This case is disposed, so no further action can be logged." : "Pick the institution in Needs review first; then actions can be logged."}</p></Panel>;
  }
  const allowed = new Set(types.data.map((t) => t.action_type));
  const groups = GROUPS.map((g) => ({ ...g, options: Object.keys(g.actions).filter((a) => allowed.has(a)) })).filter((g) => g.options.length);
  const onlyEscalate = types.data.length === 1;
  const other = caseData.assigned_bureau === "RB" ? "PGRC" : "RB";
  const target = toBureau || other;
  const current = groups.find((g) => g.key === (group || (groups.length === 1 ? groups[0].key : "")));

  async function save(e) {
    e.preventDefault();
    if (CLOSING.includes(type) && !window.confirm("Close this case as '" + type + "'? It becomes Disposed and no further action can be logged.")) return;
    setBusy(true);
    try {
      const done = await send(api, `/api/cases/${caseData.hub_case_id}/actions`, {
        action_type: type, remarks, doc_ref: doc, to_bureau: type === "Transferred" ? target : null });
      const lines = [`Status is now ${done.status}.`, ...done.alerts_created.map((a) => "⚠ " + a.message)];
      toast({ tone: done.alerts_created.length ? "error" : "success", title: `✓ Action logged: ${done.action_type}`, lines });
      setGroup(""); setType(""); setRemarks(""); setDoc(""); setToBureau("");
      onDone();
    } catch (err) {
      toast({ tone: "error", title: "Could not log the action", lines: [err.message] });
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel title="Take action on this case">
      {onlyEscalate && <p className="mb-3 rounded bg-blue-50 p-2 text-sm text-blue-900">As {user.role_label} you can only escalate a case. Day-to-day actions are taken by the bureau handling it.</p>}
      <form onSubmit={save} className="space-y-4">
        {groups.length > 1 && (
          <div>
            <div className="mb-1 text-sm font-medium">1. What do you want to do?</div>
            <div className="flex flex-wrap gap-2">
              {groups.map((g) => (
                <button type="button" key={g.key} onClick={() => { setGroup(g.key); setType(""); }}
                  className={"rounded-full border px-3 py-1.5 text-sm " + (current && current.key === g.key ? "bg-slate-900 text-white" : "bg-white hover:bg-slate-100")}>{g.title}</button>
              ))}
            </div>
          </div>
        )}
        {current && (
          <div>
            <div className="mb-1 text-sm font-medium">{groups.length > 1 ? "2. " : "1. "}Choose the action <span className="font-normal text-slate-500">· {current.help}</span></div>
            <div className="space-y-1" id="action-options">
              {current.options.map((a) => (
                <label key={a} className={"flex cursor-pointer items-start gap-2 rounded border p-2 text-sm " + (type === a ? "border-slate-900 bg-slate-50" : "hover:bg-slate-50")}>
                  <input type="radio" name="action" className="mt-1" checked={type === a} onChange={() => setType(a)} />
                  <span><span className="font-medium">{a}</span><span className="block text-xs text-slate-500">{current.actions[a]}</span></span>
                </label>
              ))}
            </div>
          </div>
        )}
        {type === "Transferred" && (
          <label className="block text-sm">Transfer to
            <select value={target} onChange={(e) => setToBureau(e.target.value)} className="ml-2 rounded border px-2 py-1.5 text-sm">
              {["RB", "PGRC"].filter((b) => b !== caseData.assigned_bureau).map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
          </label>
        )}
        {type && (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <input id="action-remarks" required={NEEDS_REMARKS.includes(type)} value={remarks} maxLength={500} onChange={(e) => setRemarks(e.target.value)}
                placeholder={NEEDS_REMARKS.includes(type) ? "Remarks (required: say why)" : "Remarks (optional)"} className="rounded border px-3 py-2 text-sm" />
              <input value={doc} maxLength={200} onChange={(e) => setDoc(e.target.value)} placeholder="Document reference (optional)" className="rounded border px-3 py-2 text-sm" />
            </div>
            <p className="text-sm text-slate-700">{effectText(type, caseData.status, target)}</p>
            <button disabled={busy} className="rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-40">{busy ? "Saving…" : "Log action"}</button>
          </>
        )}
      </form>
    </Panel>
  );
}

// Downloads this case as a printable report (HTML; open it and use Print / Save as PDF).
function DownloadCaseFile({ caseData }) {
  const { api, user } = useAuth();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  if (!user.permissions.can_export) return null;
  async function download() {
    setBusy(true);
    try {
      const r = await api(`/api/cases/${caseData.hub_case_id}/file`);
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "Download failed");
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url; a.download = caseData.source_case_no + "_case_file.html"; a.click();
      URL.revokeObjectURL(url);
      toast({ title: "Case file downloaded", lines: ["Open it in your browser. Use Print / Save as PDF in the page for a PDF. The download is recorded in the audit trail."] });
    } catch (e) {
      toast({ title: "Could not download", lines: [e.message], tone: "error" });
    } finally { setBusy(false); }
  }
  return <button id="download-case-file" onClick={download} disabled={busy} className="rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-40">{busy ? "Preparing…" : "Download case file"}</button>;
}

export default function CaseDetail() {
  const { id } = useParams();
  const [linkType, setLinkType] = useState("");
  const [linkStatus, setLinkStatus] = useState("");
  const c = useGet("/api/cases/" + id);
  if (!c.data) return <Loading state={c} />;
  const d = c.data;
  const p = d.priority;
  const shownLinks = d.links.filter((l) => (!linkType || l.link_type === linkType) && (!linkStatus || l.status === linkStatus));
  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link to="/cases" className="text-sm text-blue-700 hover:underline">← Cases</Link>
          <h1 className="mt-1 text-xl font-semibold">{d.source_case_no} <span className="text-sm font-normal text-slate-400">{d.hub_case_id}</span></h1>
          <p className="text-slate-700">{d.title}</p>
        </div>
        <DownloadCaseFile caseData={d} />
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

      <Panel title={"Linked and suggested cases (" + shownLinks.length + (shownLinks.length === d.links.length ? "" : " of " + d.links.length) + ")"}
        right={d.links.length > 0 && (
          <div className="flex gap-2">
            <select id="link-type" className="rounded border bg-white px-2 py-1.5 text-sm" value={linkType} onChange={(e) => setLinkType(e.target.value)}>
              <option value="">All types</option>
              {["CROSS_BUREAU", "CONFLICT", "DUPLICATE_ACTION", "SAME_REPORTER", "CORROBORATION"].map((t) => (
                <option key={t} value={t}>{LINK_TYPE[t]} ({d.links.filter((l) => l.link_type === t).length})</option>))}
            </select>
            <select id="link-status" className="rounded border bg-white px-2 py-1.5 text-sm" value={linkStatus} onChange={(e) => setLinkStatus(e.target.value)}>
              <option value="">All statuses</option>
              {[["SUGGESTED", "Suggested"], ["CONFIRMED", "Confirmed"], ["REJECTED", "Rejected"]].map(([k, label]) => (
                <option key={k} value={k}>{label} ({d.links.filter((l) => l.status === k).length})</option>))}
            </select>
          </div>)}>
        {d.links.length === 0 && <p className="text-sm text-slate-500">No overlaps or duplicates suggested for this case.</p>}
        {d.links.length > 0 && shownLinks.length === 0 && <p className="text-sm text-slate-500">No linked cases match this filter.</p>}
        <div className="space-y-3">{shownLinks.map((l) => <LinkCard key={l.id} link={l} onChanged={c.reload} />)}</div>
      </Panel>
    </div>
  );
}
