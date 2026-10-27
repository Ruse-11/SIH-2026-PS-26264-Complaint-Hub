import { useEffect, useState } from "react";
import { ToastProvider } from "./components/ui.jsx";
import { Navigate, NavLink, Outlet, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Cases from "./pages/Cases.jsx";
import CaseDetail from "./pages/CaseDetail.jsx";
import InstitutionProfile from "./pages/InstitutionProfile.jsx";
import Overlaps from "./pages/Overlaps.jsx";
import Alerts from "./pages/Alerts.jsx";
import Reports from "./pages/Reports.jsx";
import Insights from "./pages/Insights.jsx";
import Audit from "./pages/Audit.jsx";
import NeedsReview from "./pages/NeedsReview.jsx";
import GraphView from "./pages/GraphView.jsx";
import AttentionIndex from "./pages/AttentionIndex.jsx";

// Sidebar links: [path, label]
const NAV = [
  ["/", "Dashboard"],
  ["/cases", "Cases"],
  ["/overlaps", "Overlaps"],
  ["/alerts", "Alerts"],
  ["/needs-review", "Needs review"],
  ["/reports", "Reports"],
  ["/insights", "Insights"],
  ["/audit", "Audit trail", ["senior_management", "competent_authority"]],
  ["/graph", "Graph (later)"],
  ["/attention", "Attention (later)"],
];

// Small badge in the header: calls the hub's /api/health through the dev proxy.
function HubStatus() {
  const [state, setState] = useState("checking");
  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then((d) => setState(d.status === "ok" ? "online v" + d.version : "error"))
      .catch(() => setState("offline"));
  }, []);
  const ok = state.startsWith("online");
  return (
    <span className={"rounded-full px-3 py-1 text-xs " + (ok ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800")}>
      Hub: {state}
    </span>
  );
}

// Words shown in the header under the user's name: what this role is allowed to see.
const SCOPE_TEXT = {
  bureau: "own bureau's cases",
  assigned: "cases assigned to the bureau",
  region: "own region only",
  all: "all cases",
};

// Permissions that change data. A role with none of them is read-only.
const ACTIONS = ["can_log_actions", "can_decide_links", "can_transfer", "can_escalate", "can_decide_lead"];

// Sidebar + header around every page after login.
function Shell() {
  const { user, logout } = useAuth();
  const perms = user.permissions;
  return (
    <ToastProvider>
    <div className="min-h-screen text-slate-900">
      <div className="tricolour"><i /><i /><i /></div>
      <div className="border-b bg-slate-50 px-6 py-1 text-xs text-slate-600">
        <div className="mx-auto flex max-w-screen-2xl items-center gap-4">
          <span>Officers decide. The system only suggests.</span>
          <span className="rounded border border-dashed border-amber-600 bg-amber-50 px-2 font-semibold text-amber-800">PROTOTYPE · synthetic data</span>
          <span className="flex-1" />
          <HubStatus />
        </div>
      </div>
      <header className="gov-head">
        <div className="mx-auto flex max-w-screen-2xl items-center gap-4 px-6 py-3">
          <div className="seal" aria-hidden="true">CH</div>
          <div className="leading-tight">
            <div className="text-[11px] uppercase tracking-wider text-blue-200">Technical Education Regulator (fictional)</div>
            <div className="text-xl font-bold text-white">Integrated Complaint Monitoring Hub</div>
            <div className="text-xs text-blue-100">Regulation Bureau · Public Grievance Redressal Cell · Other bureaus and regional offices</div>
          </div>
          <div className="flex-1" />
          <div className="text-right leading-tight text-blue-50">
            <div className="text-sm font-semibold">{user.display_name}</div>
            <div className="text-xs text-blue-200">
              {user.role_label} · sees {SCOPE_TEXT[perms.view_scope]}
              {perms.view_scope === "region" ? ` (${user.region})` : ""}
              {ACTIONS.some((k) => perms[k]) ? "" : " · read-only"}
            </div>
          </div>
          <button onClick={logout} className="rounded border border-blue-300 px-3 py-1 text-sm text-white hover:bg-blue-800">Log out</button>
        </div>
      </header>
      <nav className="gov-nav" aria-label="Main">
        <div className="mx-auto flex max-w-screen-2xl flex-wrap items-center px-6">
          {NAV.filter(([, , roles]) => !roles || roles.includes(user.role)).map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => "gov-tab" + (isActive ? " active" : "")}>
              {label}
            </NavLink>
          ))}
        </div>
      </nav>
      <main className="mx-auto max-w-screen-2xl p-6">
        <Outlet />
      </main>
      <footer className="gov-foot">
        <div className="mx-auto flex max-w-screen-2xl flex-wrap justify-between gap-2 px-6 py-4">
          <span>Integrated Complaint Monitoring Hub · SIH 2026 · PS 26264 · all data is synthetic</span>
          <span>Every suggestion is confirmed or rejected by an officer, and every decision is in the audit trail.</span>
        </div>
      </footer>
    </div>
    </ToastProvider>
  );
}

// Pages after login need a logged-in user; otherwise go to the login page.
function RequireAuth() {
  const { user, ready } = useAuth();
  if (!ready) return <div className="p-8 text-slate-500">Loading…</div>;
  return user ? <Shell /> : <Navigate to="/login" replace />;
}

export default function App() {
  const { user, ready } = useAuth();
  if (!ready) return <div className="p-8 text-slate-500">Loading…</div>;
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
      <Route element={<RequireAuth />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/cases" element={<Cases />} />
          <Route path="/cases/:id" element={<CaseDetail />} />
          <Route path="/institutions/:id" element={<InstitutionProfile />} />
          <Route path="/overlaps" element={<Overlaps />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/insights" element={<Insights />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="/needs-review" element={<NeedsReview />} />
          <Route path="/graph" element={<GraphView />} />
          <Route path="/attention" element={<AttentionIndex />} />
      </Route>
    </Routes>
  );
}
