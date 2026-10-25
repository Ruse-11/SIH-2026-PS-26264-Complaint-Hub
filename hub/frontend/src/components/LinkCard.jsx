// One suggested link between two cases, with the reasons and Confirm / Reject buttons for officers.
import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { LINK_TYPE, StatusBadge, send } from "./ui.jsx";

const HEADLINE = {
  CROSS_BUREAU: "Potential Overlapping Cases – Coordination Required",
  SAME_REPORTER: "Possible duplicate: same reporter on both portals",
  CORROBORATION: "Possible corroboration: independent reporters, similar complaint",
};

function Reasons({ link }) {
  const r = link.reasons || {};
  return (
    <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
      {link.link_type === "CROSS_BUREAU" ? (
        <>
          <li>Open cases in two bureaus ({(r.bureaus || []).join(" and ")}) at the same college.</li>
          <li>{r.same_category ? "Same category: " + (r.categories || [])[0] : "Different categories: " + (r.categories || []).join(" / ")}. No text match is needed for this check.</li>
          {r.suggested_lead && (
            <li>Suggested lead (suggestion only): <b>{r.suggested_lead.bureau || "none"}</b>. {r.suggested_lead.rule}</li>
          )}
        </>
      ) : (
        <>
          <li>Text similarity {link.score} (shared words: {(r.shared_keywords || []).join(", ") || "none"}).</li>
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
  const [busy, setBusy] = useState(false);
  const canDecide = user.permissions.can_decide_links && link.status === "SUGGESTED";

  async function decide(kind) {
    setBusy(true);
    setError("");
    try {
      await send(api, `/api/matching/links/${link.id}/${kind}`, { note });
      onChanged && onChanged();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div id={"link-" + link.id} className={"rounded-lg border p-4 " + (highlight ? "border-blue-500 bg-blue-50" : "bg-white")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="font-medium text-slate-900">{HEADLINE[link.link_type] || LINK_TYPE[link.link_type]}</div>
          <div className="text-xs text-slate-500">{LINK_TYPE[link.link_type]} · suggestion #{link.id}</div>
        </div>
        <span className={"rounded-full px-2 py-0.5 text-xs font-medium " + (link.status === "CONFIRMED" ? "bg-green-100 text-green-800" : link.status === "REJECTED" ? "bg-slate-200 text-slate-700" : "bg-amber-100 text-amber-800")}>
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
      {link.status !== "SUGGESTED" && <p className="mt-2 text-xs text-slate-500">Decided by {link.decided_by} on {String(link.decided_at).slice(0, 10)}.</p>}
      {canDecide && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input className="min-w-48 flex-1 rounded border px-3 py-1.5 text-sm" placeholder="Note (optional)" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
          <button disabled={busy} onClick={() => decide("confirm")} className="rounded bg-green-700 px-3 py-1.5 text-sm text-white disabled:opacity-50">Confirm link</button>
          <button disabled={busy} onClick={() => decide("reject")} className="rounded border border-slate-400 px-3 py-1.5 text-sm disabled:opacity-50">Reject</button>
        </div>
      )}
      {error && <p className="mt-2 rounded bg-red-100 px-3 py-1 text-sm text-red-800">{error}</p>}
    </div>
  );
}
