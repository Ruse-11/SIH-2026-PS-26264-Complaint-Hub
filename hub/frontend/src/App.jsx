import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Cases from "./pages/Cases.jsx";
import CaseDetail from "./pages/CaseDetail.jsx";
import InstitutionProfile from "./pages/InstitutionProfile.jsx";
import Overlaps from "./pages/Overlaps.jsx";
import Alerts from "./pages/Alerts.jsx";
import Reports from "./pages/Reports.jsx";
import Insights from "./pages/Insights.jsx";
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

export default function App() {
  return (
    <div className="flex min-h-screen bg-slate-100 text-slate-900">
      <aside className="w-56 shrink-0 bg-slate-900 p-4 text-slate-200">
        <div className="mb-6 text-lg font-semibold">Complaint Hub</div>
        <nav className="flex flex-col gap-1">
          {NAV.map(([to, label]) => (
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
        <header className="flex items-center justify-between border-b bg-white px-6 py-3">
          <span className="text-sm text-slate-500">Officers decide. The system only suggests. (synthetic data)</span>
          <HubStatus />
        </header>
        <main className="p-6">
          <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<Dashboard />} />
          <Route path="/cases" element={<Cases />} />
          <Route path="/cases/:id" element={<CaseDetail />} />
          <Route path="/institutions/:id" element={<InstitutionProfile />} />
          <Route path="/overlaps" element={<Overlaps />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/insights" element={<Insights />} />
          <Route path="/needs-review" element={<NeedsReview />} />
          <Route path="/graph" element={<GraphView />} />
          <Route path="/attention" element={<AttentionIndex />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
