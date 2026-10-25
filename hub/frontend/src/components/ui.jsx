// Small shared pieces for every page: data loading hook, status badge, tiles, labels.
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth.jsx";

// GET a hub URL and keep {data, error, loading}. Call reload() after a change (e.g. confirming a link).
export function useGet(path) {
  const { api } = useAuth();
  const [state, setState] = useState({ data: null, error: "", loading: true });
  const load = useCallback(() => {
    if (!path) return;
    setState((s) => ({ ...s, loading: true, error: "" }));
    api(path)
      .then(async (r) => {
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(body.detail || "Request failed (" + r.status + ")");
        setState({ data: body, error: "", loading: false });
      })
      .catch((e) => setState({ data: null, error: e.message, loading: false }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);
  useEffect(load, [load]);
  return { ...state, reload: load };
}

// POST/JSON helper that throws the hub's error message.
export async function send(api, path, body) {
  const r = await api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Request failed (" + r.status + ")");
  return data;
}

const STATUS_STYLE = {
  Pending: "bg-amber-100 text-amber-800",
  "Under Process": "bg-blue-100 text-blue-800",
  Disposed: "bg-green-100 text-green-800",
  Transferred: "bg-purple-100 text-purple-800",
  Escalated: "bg-red-100 text-red-800",
  unverified_institution: "bg-slate-200 text-slate-700",
};
export function StatusBadge({ status }) {
  const label = status === "unverified_institution" ? "Needs review" : status;
  return <span className={"rounded-full px-2 py-0.5 text-xs font-medium " + (STATUS_STYLE[status] || "bg-slate-100")}>{label}</span>;
}

export function Tile({ label, value, tone = "slate", to, hint }) {
  const tones = { slate: "text-slate-900", red: "text-red-700", amber: "text-amber-700", green: "text-green-700", blue: "text-blue-700", purple: "text-purple-700" };
  const body = (
    <div className="rounded-xl bg-white p-4 shadow-sm hover:shadow">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className={"mt-1 text-3xl font-semibold " + tones[tone]}>{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
  return to ? <Link to={to}>{body}</Link> : body;
}

export function Panel({ title, right, children }) {
  return (
    <section className="rounded-xl bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="font-medium text-slate-800">{title}</h2>
        {right}
      </div>
      {children}
    </section>
  );
}

export function Loading({ state }) {
  if (state.loading && !state.data) return <div className="text-slate-500">Loading…</div>;
  if (state.error) return <div className="rounded bg-red-100 px-4 py-2 text-sm text-red-800">{state.error}</div>;
  return null;
}

export const LINK_TYPE = {
  CROSS_BUREAU: "Cross-bureau overlap",
  SAME_REPORTER: "Same reporter, duplicate",
  CORROBORATION: "Corroboration",
  CONFLICT: "Conflict",
};

export const fmtDate = (d) => (d ? String(d).slice(0, 10) : "–");
