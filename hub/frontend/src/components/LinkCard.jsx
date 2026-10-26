// One suggested link between two cases, with the reasons and Confirm / Reject buttons for officers.
import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { BUREAUS, LINK_TYPE, StatusBadge, send, useToast } from "./ui.jsx";

const HEADLINE = {
  CROSS_BUREAU: "Potential Overlapping Cases – Coordination Required",
  SAME_REPORTER: "Possible duplicate: same reporter on both portals",
  CORROBORATION: "Possible corroboration: independent reporters, similar complaint",
  CONFLICT: "Conflicting actions by two bureaus – decision needed",
  DUPLICATE_ACTION: "Possible duplicate action by two bureaus",
  RELATED: "Related cases linked by an officer",
};

const ACTION_TEXT = (a) => `${a.bureau} · ${a.action_type} (${a.stance.toLowerCase()}) on ${a.case}, ${a.date}`;

// The lead-bureau suggestion (shown by the rule that fired) and, for the competent authority, the final decision.
function LeadPanel({ link, onChanged }) {
  const { user, api } = useAuth();
  const toast = useToast();
  const [bureau, setBureau] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const r = link.reasons || {};
  const lead = r.suggested_lead;
  if (!lead) return null;
  async function decide() {
    setBusy(true);
    try {
      await send(api, `/api/conflicts/${link.id}/lead`, { bureau, note });
      toast({ tone: "success", title: "✓ Lead bureau recorded", lines: [`${bureau} will lead. The system suggested ${lead.bureau || "no lead"}; your decision is kept in the audit trail.`] });
      onChanged && onChanged();
    } catch (e) {
      toast({ tone: "error", title: "Could not save the decision", lines: [e.message] });
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="mt-3 rounded border bg-slate-50 p-3 text-sm">
      <div><b>Suggested lead bureau (suggestion only):</b> {lead.bureau || "none"}. <span className="text-slate-600">{lead.rule}</span></div>
      {r.final_lead ? (
        <div className="mt-1 text-green-800"><b>Final decision:</b> {r.final_lead.bureau} leads, decided by {r.final_lead.decided_by} on {r.final_lead.decided_at.slice(0, 10)}{r.final_lead.note ? ` ("${r.final_lead.note}")` : ""}.</div>
      ) : user.permissions.can_decide_lead ? (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <select className="rounded border px-2 py-1" value={bureau} onChange={(e) => setBureau(e.target.value)}>
            <option value="">Decide the lead bureau…</option>{BUREAUS.map((b) => <option key={b}>{b}</option>)}
          </select>
          <input className="min-w-40 flex-1 rounded border px-2 py-1" placeholder="Reason (optional)" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
          <button disabled={!bureau || busy} onClick={decide} className="rounded bg-slate-900 px-3 py-1 text-white disabled:opacity-40">{busy ? "Saving…" : "Record decision"}</button>
        </div>
      ) : <div className="mt-1 text-xs text-slate-500">If the bureaus disagree, the competent authority decides.</div>}
    </div>
  );
}

function Reasons({ link }) {
  const r = link.reasons || {};
  return (
    <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
      {r.manual ? (
        <>
          <li>Linked by {r.created_by} (an officer's own decision, not a system suggestion).</li>
          <li>Reason given: {r.note}</li>
        </>
      ) : link.link_type === "CONFLICT" || link.link_type === "DUPLICATE_ACTION" ? (
        <>
          <li>{r.rule}</li>
          {(r.matches || []).slice(0, 2).map((m, i) => link.link_type === "CONFLICT"
            ? <li key={i}>Enforcing: {ACTION_TEXT(m.enforcing)}. Closing: {ACTION_TEXT(m.closing)}. {m.gap_days} day(s) apart (rule window {r.window_days} days).</li>
            : <li key={i}>{ACTION_TEXT(m.first)} and {ACTION_TEXT(m.second)}. {m.gap_days} day(s) apart (rule window {r.window_days} days).</li>)}
          <li>Same college, same category ({r.category}), different bureaus.</li>
        </>
      ) : link.link_type === "CROSS_BUREAU" ? (
        <>
          <li>Open cases in two bureaus ({(r.bureaus || []).join(" and ")}) at the same college.</li>
          <li>{r.same_category ? "Same category: " + (r.categories || [])[0] : "Different categories: " + (r.categories || []).join(" / ")}. No text match is needed for this check.</li>
        </>
      ) : (
        <>
          <li>Text similarity {link.score}{r.method ? (r.method === "embeddings" ? " (AI embeddings + keywords)" : " (keywords)") : ""} (shared words: {(r.shared_keywords || []).join(", ") || "none"}).</li>
          <li>{r.same_reporter ? "Same reporter" : "Different reporters"}, category {r.category}.</li>
        </>
      )}
    </ul>
  );
}

export default function LinkCard({ link, onChanged, highlight }) {
  const { user, api } = useAuth();
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const toast = useToast();
  const canDecide = user.permissions.can_decide_links && link.status === "SUGGESTED";

  async function decide(kind) {
    setBusy(kind);
    setError("");
    try {
      const done = await send(api, `/api/matching/links/${link.id}/${kind}`, { note });
      const names = done.cases.map((c) => c.source_case_no).join(" and ");
      const lines = [];
      if (kind === "confirm") {
        lines.push(`${names} are now linked.`);
        if (done.cluster_id) lines.push(`They are part of corroboration cluster #${done.cluster_id}.`);
        lines.push(done.priority_changes.length
          ? "Priority: " + done.priority_changes.map((c) => `${c.source_case_no} ${c.before} → ${c.after}`).join(", ")
          : "No priority change (only confirmed corroboration raises priority).");
        toast({ tone: "success", title: "✓ Link confirmed", lines: [...lines, "Recorded in the audit trail."] });
      } else {
        toast({ tone: "neutral", title: "Suggestion rejected", lines: [`${names} will not be suggested together again.`, "Recorded in the audit trail."] });
      }
      onChanged && onChanged();
    } catch (e) {
      setError(e.message);
      toast({ tone: "error", title: "Could not save the decision", lines: [e.message] });
    } finally {
      setBusy("");
    }
  }

  return (
    <div id={"link-" + link.id} className={"rounded-lg border p-4 " + (highlight ? "border-blue-500 bg-blue-50" : "bg-white")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="font-medium text-slate-900">{HEADLINE[link.link_type] || LINK_TYPE[link.link_type]}</div>
          <div className="text-xs text-slate-500">{LINK_TYPE[link.link_type]} · suggestion #{link.id}</div>
        </div>
        <span className={"rounded-full px-2 py-0.5 text-xs font-medium " + (link.link_type === "CONFLICT" && link.status === "SUGGESTED" ? "bg-red-100 text-red-800" : link.status === "CONFIRMED" ? "bg-green-100 text-green-800" : link.status === "REJECTED" ? "bg-slate-200 text-slate-700" : "bg-amber-100 text-amber-800")}>
          {link.status === "SUGGESTED" ? "Waiting for officer" : link.status.toLowerCase()}
        </span>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        {link.cases.map((c) => (
          <div key={c.hub_case_id} className="rounded border bg-slate-50 p-3 text-sm">
            <Link className="font-medium text-blue-700 hover:underline" to={"/cases/" + c.hub_case_id}>{c.source_case_no}</Link>{" "}
            <span className="text-xs text-slate-500">{c.bureau} · {c.received_at}</span>
            <div>{c.title}</div>
            <div className="mt-1 flex gap-2 text-xs text-slate-500"><span>{c.category}</span><StatusBadge status={c.status} /></div>
          </div>
        ))}
      </div>
      <Reasons link={link} />
      {["CROSS_BUREAU", "CONFLICT", "DUPLICATE_ACTION"].includes(link.link_type) && <LeadPanel link={link} onChanged={onChanged} />}
      {link.status !== "SUGGESTED" && <p className="mt-2 text-xs text-slate-500">Decided by {link.decided_by} on {String(link.decided_at).slice(0, 10)}.</p>}
      {canDecide && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input className="min-w-48 flex-1 rounded border px-3 py-1.5 text-sm" placeholder="Note (optional)" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
          <button disabled={!!busy} onClick={() => decide("confirm")} className="rounded bg-green-700 px-3 py-1.5 text-sm text-white disabled:opacity-50">{busy === "confirm" ? "Saving…" : "Confirm link"}</button>
          <button disabled={!!busy} onClick={() => decide("reject")} className="rounded border border-slate-400 px-3 py-1.5 text-sm disabled:opacity-50">{busy === "reject" ? "Saving…" : "Reject"}</button>
        </div>
      )}
      {error && <p className="mt-2 rounded bg-red-100 px-3 py-1 text-sm text-red-800">{error}</p>}
    </div>
  );
}
