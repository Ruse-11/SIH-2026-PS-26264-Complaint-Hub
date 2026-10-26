// Small shared pieces for every page: data loading hook, status badge, tiles, labels.
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth.jsx";

// GET a hub URL and keep {data, error, loading}. Call reload() after a change (e.g. confirming a link).
export function useGet(path, options = {}) {
  const { api } = useAuth();
  const every = options.every || 0;  // seconds; 0 = load once. Used by the dashboard and alerts to stay "real time".
  const [state, setState] = useState({ data: null, error: "", loading: true, updatedAt: null });
  const latest = useRef(0);  // only the newest request may update the screen (a slow old answer must not overwrite a newer one)
  const load = useCallback((silent = false) => {
    if (!path) return;
    const mine = ++latest.current;
    if (silent !== true) setState((s) => ({ ...s, loading: true, error: "" }));  // a background refresh must not flash "Loading"
    api(path)
      .then(async (r) => {
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(body.detail || "Request failed (" + r.status + ")");
        if (mine === latest.current) setState({ data: body, error: "", loading: false, updatedAt: new Date() });
      })
      .catch((e) => {
        if (mine !== latest.current) return;
        if (silent === true) return;  // keep showing the last good data; the next tick tries again
        setState({ data: null, error: e.message, loading: false, updatedAt: null });
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!every || !path) return undefined;
    const t = setInterval(() => { if (!document.hidden) load(true); }, every * 1000);
    return () => clearInterval(t);
  }, [every, path, load]);
  return { ...state, reload: () => load() };
}

// "Updated 10:32:05 · refreshes every 60 s" with a Refresh now button. Shows that the screen is live.
export function LiveStamp({ state, every = 60 }) {
  if (!state.updatedAt) return null;
  return (
    <span className="text-xs text-slate-500">
      Updated {state.updatedAt.toLocaleTimeString()} · refreshes every {every} s{" "}
      <button onClick={state.reload} className="text-blue-700 hover:underline">Refresh now</button>
    </span>
  );
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
  CONFLICT: "Conflicting actions",
  DUPLICATE_ACTION: "Duplicate action",
  RELATED: "Related (linked by an officer)",
};

// Bureaus a case can be assigned or transferred to (QAC = Quality Assurance Cell, the demo "other bureau").
export const BUREAUS = ["RB", "PGRC", "QAC"];
export const BUREAU_NAME = { RB: "Regulation Bureau", PGRC: "Public Grievance Redressal Cell", QAC: "Quality Assurance Cell" };

export const fmtDate = (d) => (d ? String(d).slice(0, 10) : "–");

// ---- toast: a message that appears top-right for a few seconds (feedback after Confirm / Reject) ----
const ToastContext = createContext(() => {});
export const useToast = () => useContext(ToastContext);

export function ToastProvider({ children }) {
  const [toast, setToast] = useState(null);
  const timer = useRef(null);
  const show = useCallback((t) => {
    clearTimeout(timer.current);
    setToast(t);
    timer.current = setTimeout(() => setToast(null), 9000);
  }, []);
  const tones = { success: "border-green-600 bg-green-50", neutral: "border-slate-500 bg-white", error: "border-red-600 bg-red-50" };
  return (
    <ToastContext.Provider value={show}>
      {children}
      {toast && (
        <div role="status" id="toast" className={"fixed right-6 top-20 z-50 max-w-sm rounded-lg border-l-4 p-4 shadow-xl " + tones[toast.tone || "success"]}>
          <div className="flex items-start justify-between gap-3">
            <div className="font-semibold text-slate-900">{toast.title}</div>
            <button aria-label="Close" className="text-slate-500 hover:text-slate-900" onClick={() => setToast(null)}>×</button>
          </div>
          {(toast.lines || []).map((l, i) => <div key={i} className="mt-1 text-sm text-slate-700">{l}</div>)}
        </div>
      )}
    </ToastContext.Provider>
  );
}
