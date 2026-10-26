// Reports screen (M11): pick a report, optionally a date, see the table, download CSV if the role may export.
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import InstitutionSuggest from "../components/InstitutionSuggest.jsx";
import { Loading, Panel, StatusBadge, useGet, useToast } from "../components/ui.jsx";

// How one cell is drawn: links for IDs, badge for status, dash for empty.
function Cell({ col, row }) {
  const v = row[col];
  if (v === null || v === undefined || v === "") return <span className="text-slate-400">–</span>;
  if (col === "hub_case_id") return <Link className="text-blue-700 hover:underline" to={"/cases/" + v}>{v}</Link>;
  if (col === "status") return <StatusBadge status={v} />;
  return String(v);
}

export default function Reports() {
  const { api, user } = useAuth();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const key = params.get("report") || "bureau";
  const asOf = params.get("as_of") || "";
  const instId = params.get("institution_id") || "";
  const [instText, setInstText] = useState("");
  const [busy, setBusy] = useState(false);

  const catalogue = useGet("/api/reports");
  const current = (catalogue.data || []).find((c) => c.key === key);
  const needsInst = current && current.needs === "institution_id";
  const qs = new URLSearchParams();
  if (asOf) qs.set("as_of", asOf);
  if (instId) qs.set("institution_id", instId);
  const query = qs.toString() ? "?" + qs.toString() : "";
  const report = useGet(catalogue.data ? "/api/reports/" + key + query : null);
  const set = (patch) => { const p = new URLSearchParams(params); Object.entries(patch).forEach(([k, v]) => (v ? p.set(k, v) : p.delete(k))); setParams(p); };
  const canExport = user.permissions.can_export;

  // Download through fetch so the login token is sent; then save the file from a blob.
  async function download() {
    setBusy(true);
    try {
      const sep = query ? "&" : "?";
      const r = await api("/api/reports/" + key + query + sep + "format=csv");
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "Export failed");
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url; a.download = key + "_" + (report.data ? report.data.as_of : "report") + ".csv"; a.click();
      URL.revokeObjectURL(url);
      toast({ title: "CSV downloaded", lines: ["The export is recorded in the audit trail."] });
    } catch (e) {
      toast({ title: "Could not export", lines: [e.message], tone: "error" });
    } finally { setBusy(false); }
  }

  const data = report.data;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Reports</h1>
      <Loading state={catalogue} />
      {catalogue.data && (
        <Panel title="Choose a report">
          <div className="flex flex-wrap items-end gap-4">
            <label className="text-sm">
              <div className="mb-1 text-slate-500">Report</div>
              <select id="report-select" className="rounded border px-3 py-2" value={key} onChange={(e) => set({ report: e.target.value, institution_id: "" })}>
                {catalogue.data.map((c) => <option key={c.key} value={c.key}>{c.title}</option>)}
              </select>
            </label>
            <label className="text-sm">
              <div className="mb-1 text-slate-500">As of date (optional)</div>
              <input id="report-asof" type="date" className="rounded border px-3 py-2" value={asOf} onChange={(e) => set({ as_of: e.target.value })} />
            </label>
            {needsInst && (
              <div className="min-w-72 text-sm">
                <div className="mb-1 text-slate-500">Institution</div>
                <InstitutionSuggest id="report-institution" value={instText} onChange={setInstText} placeholder="Type a college name or AICTE ID…"
                  onPick={(c) => { setInstText(c.official_name); set({ institution_id: c.aicte_id }); }} onSubmit={() => {}} />
              </div>
            )}
            <div className="ml-auto">
              {canExport
                ? <button id="export-csv" disabled={busy || !data || (needsInst && !instId)} onClick={download}
                    className="rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-40">{busy ? "Preparing…" : "Download CSV"}</button>
                : <span className="text-xs text-slate-500">Your role can view reports but not export them.</span>}
            </div>
          </div>
          {current && <p className="mt-3 text-sm text-slate-600">{current.description}</p>}
        </Panel>
      )}
      {needsInst && !instId && <div className="rounded bg-amber-50 px-4 py-3 text-sm text-amber-900">Choose an institution to see its complaint history.</div>}
      {!(needsInst && !instId) && <Loading state={report} />}
      {data && !(needsInst && !instId) && (
        <Panel title={data.title} right={<span className="text-xs text-slate-500">As of {data.as_of} · {data.rows.length} rows</span>}>
          {data.rows.length === 0 ? <div className="text-sm text-slate-500">Nothing to show for your role.</div> : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm" id="report-table">
                <thead><tr className="border-b text-xs uppercase text-slate-500">
                  {data.columns.map((c) => <th key={c.key} className="whitespace-nowrap px-2 py-2">{c.label}</th>)}
                </tr></thead>
                <tbody>
                  {data.rows.map((row, i) => (
                    <tr key={i} className="border-b last:border-0 hover:bg-slate-50">
                      {data.columns.map((c) => <td key={c.key} className="px-2 py-2 align-top"><Cell col={c.key} row={row} /></td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {data.note && <p className="mt-3 text-xs text-slate-500">{data.note}</p>}
        </Panel>
      )}
    </div>
  );
}
