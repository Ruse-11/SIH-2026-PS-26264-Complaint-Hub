// Needs review: complaints whose college the reporter could not identify. The officer picks the college;
// the name the reporter typed is saved as a learned alias so the next reporter finds it.
import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { Loading, Panel, fmtDate, send, useGet } from "../components/ui.jsx";

function Row({ item, canAssign, onDone }) {
  const { api } = useAuth();
  const typed = item.typed_details || {};
  const [q, setQ] = useState(typed.typed_name || "");
  const [cards, setCards] = useState([]);
  const [msg, setMsg] = useState("");

  async function find(e) {
    e.preventDefault();
    const r = await fetch("/api/institutions/search?q=" + encodeURIComponent(q));
    const data = await r.json();
    setCards(data.candidates || []);
    setMsg(data.outcome === "NOT_LISTED" ? "No matching college. Try fewer words." : "");
  }
  async function assign(id) {
    try {
      await send(api, `/api/cases/${item.hub_case_id}/assign-institution`, { institution_id: id });
      onDone();
    } catch (err) {
      setMsg(err.message);
    }
  }

  return (
    <div className="rounded-lg border bg-white p-4">
      <div className="flex flex-wrap justify-between gap-2">
        <div><Link className="font-medium text-blue-700 hover:underline" to={"/cases/" + item.hub_case_id}>{item.source_case_no}</Link> · {item.assigned_bureau} · {item.category} · {fmtDate(item.received_at)}</div>
      </div>
      <p className="mt-1 text-sm">{item.title}: {item.description}</p>
      <p className="mt-1 text-xs text-slate-500">The reporter typed: {Object.entries(typed).filter(([, v]) => v).map(([k, v]) => k.replace("_", " ") + " = " + v).join("; ") || "nothing"}</p>
      {canAssign ? (
        <>
          <form className="mt-3 flex gap-2" onSubmit={find}>
            <input className="flex-1 rounded border px-3 py-1.5 text-sm" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search the college registry" />
            <button className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white">Find</button>
          </form>
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            {cards.map((c) => (
              <div key={c.aicte_id} className="rounded border p-2 text-sm">
                <div className="font-medium">{c.official_name}</div>
                <div className="text-xs text-slate-500">{c.aicte_id} · {c.district}, {c.state}</div>
                <button className="mt-2 rounded bg-green-700 px-2 py-1 text-xs text-white" onClick={() => assign(c.aicte_id)}>Assign this college</button>
              </div>
            ))}
          </div>
        </>
      ) : <p className="mt-2 text-xs text-slate-500">Only bureau officers and the competent authority can assign a college.</p>}
      {msg && <p className="mt-2 rounded bg-amber-50 px-3 py-1 text-sm text-amber-900">{msg}</p>}
    </div>
  );
}

export default function NeedsReview() {
  const { user } = useAuth();
  const list = useGet("/api/cases/needs-review");
  const canAssign = ["rb_officer", "pgrc_officer", "competent_authority"].includes(user.role);
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Needs review</h1>
      <p className="text-sm text-slate-600">The hub never guesses a college. These complaints wait here until an officer picks one.</p>
      <Loading state={list} />
      {list.data && list.data.length === 0 && <Panel title="All clear">No complaints are waiting for a college to be assigned.</Panel>}
      <div className="space-y-3">{(list.data || []).map((i) => <Row key={i.hub_case_id} item={i} canAssign={canAssign} onDone={list.reload} />)}</div>
    </div>
  );
}
