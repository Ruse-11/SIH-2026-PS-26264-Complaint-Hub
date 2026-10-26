import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";

// What each role can see, in plain words (the real rules live in the hub: GET /api/auth/me).
const SCOPE = {
  rb_officer: "RB cases; confirms or rejects links; logs actions and transfers",
  pgrc_officer: "PGRC cases; confirms or rejects links; logs actions and transfers",
  other_bureau: "Cases assigned to the bureau; overlap panel; logs actions",
  regional_office: "Own region only; views, adds remarks, escalates",
  senior_management: "Everything, read-only; KPIs, ageing, reports",
  competent_authority: "Everything; escalations; final call on the lead bureau",
};

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [demo, setDemo] = useState(null); // { password, accounts: [...] }
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch("/api/auth/demo-accounts")
      .then((r) => r.json())
      .then(setDemo)
      .catch(() => setError("Cannot reach the hub. Is `python run_all.py` running?"));
  }, []);

  async function submit(u, p) {
    setBusy(true);
    setError("");
    try {
      await login(u, p);
      navigate("/", { replace: true });
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-100">
      <div className="tricolour"><i /><i /><i /></div>
      <header className="gov-head">
        <div className="mx-auto flex max-w-3xl items-center gap-4 px-4 py-4">
          <div className="seal" aria-hidden="true">CH</div>
          <div className="leading-tight">
            <div className="text-[11px] uppercase tracking-wider text-blue-200">Technical Education Regulator (fictional)</div>
            <h1 className="text-xl font-bold text-white">Integrated Complaint Monitoring Hub</h1>
            <p className="text-xs text-blue-100">Officer sign-in · Officers decide; the system only suggests.</p>
          </div>
          <span className="ml-auto rounded border border-dashed border-amber-300 bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-800">PROTOTYPE<br />synthetic data</span>
        </div>
      </header>
      <div className="mx-auto max-w-3xl px-4 py-8">
        <div className="rounded border border-t-4 border-slate-300 border-t-blue-900 bg-white p-6">
          <h2 className="font-medium text-slate-800">Demo accounts (prototype, synthetic data)</h2>
          <p className="text-sm text-slate-500">Click a role to sign in. Password for all: {demo ? demo.password : "…"}</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {demo &&
              demo.accounts.map((a) => (
                <button
                  key={a.username}
                  disabled={busy}
                  onClick={() => submit(a.username, demo.password)}
                  className="rounded-lg border border-slate-200 p-3 text-left hover:border-slate-400 hover:bg-slate-50 disabled:opacity-50"
                >
                  <div className="font-medium text-slate-900">{a.role_label}</div>
                  <div className="text-xs text-slate-500">{a.username}</div>
                  <div className="mt-1 text-sm text-slate-600">{SCOPE[a.role]}</div>
                </button>
              ))}
          </div>
        </div>

        <form
          className="mt-4 rounded border border-t-4 border-slate-300 border-t-blue-900 bg-white p-6"
          onSubmit={(e) => {
            e.preventDefault();
            submit(username, password);
          }}
        >
          <h2 className="font-medium text-slate-800">Or sign in with a username</h2>
          <div className="mt-3 flex flex-col gap-3 sm:flex-row">
            <input className="flex-1 rounded border px-3 py-2" placeholder="Username" value={username}
              onChange={(e) => setUsername(e.target.value)} />
            <input className="flex-1 rounded border px-3 py-2" placeholder="Password" type="password" value={password}
              onChange={(e) => setPassword(e.target.value)} />
            <button disabled={busy} className="rounded bg-slate-900 px-4 py-2 text-white disabled:opacity-50">Sign in</button>
          </div>
        </form>

        {error && <p className="mt-4 rounded bg-red-100 px-4 py-2 text-sm text-red-800">{error}</p>}
      </div>
    </div>
  );
}
