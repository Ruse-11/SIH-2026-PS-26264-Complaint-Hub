import { useEffect, useState } from "react";
import InstitutionSuggest from "./components/InstitutionSuggest.jsx";
import { ToastProvider } from "./components/ui.jsx";
import { Navigate, NavLink, Outlet, Route, Routes, useNavigate } from "react-router-dom";
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

// Search box in the header: jumps to the case list filtered by what was typed (name, AICTE ID or case ID).
function HeaderSearch() {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  return (
    <InstitutionSuggest id="header-search" className="max-w-md flex-1" value={text} onChange={setText}
      placeholder="Search institution, AICTE ID or case ID…"
      onPick={(c) => { setText(""); navigate("/cases?institution_id=" + c.aicte_id); }}
      onSubmit={(t) => t && navigate("/cases?q=" + encodeURIComponent(t))} />
  );
}

// Sidebar + header around every page after login.
function Shell() {
  const { user, logout } = useAuth();
  const perms = user.permissions;
  return (
    <ToastProvider>
    <div className="flex min-h-screen bg-slate-100 text-slate-900">
      <aside className="w-56 shrink-0 bg-slate-900 p-4 text-slate-200">
        <div className="mb-6 text-lg font-semibold">Complaint Hub</div>
        <nav className="flex flex-col gap-1">
          {NAV.filter(([, , roles]) => !roles || roles.includes(user.role)).map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) => "rounded px-3 py-2 text-sm " + (isActive ? "bg-slate-700 text-white" : "hover:bg-slate-800")}
            >
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="flex-1">
        <header className="flex items-center justify-between gap-4 border-b bg-white px-6 py-3">
          <HeaderSearch />
          <span className="hidden text-sm text-slate-500 xl:inline">Officers decide. The system only suggests. (synthetic data)</span>
          <div className="flex items-center gap-3">
            <HubStatus />
            <div className="text-right leading-tight">
              <div className="text-sm font-medium">{user.display_name}</div>
              <div className="text-xs text-slate-500">
                {user.role_label} · sees {SCOPE_TEXT[perms.view_scope]}
                {perms.view_scope === "region" ? ` (${user.region})` : ""}
                {ACTIONS.some((k) => perms[k]) ? "" : " · read-only"}
              </div>
            </div>
            <button onClick={logout} className="rounded border px-3 py-1 text-sm hover:bg-slate-100">Log out</button>
          </div>
        </header>
        <main className="p-6">
          <Outlet />
        </main>
      </div>
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
