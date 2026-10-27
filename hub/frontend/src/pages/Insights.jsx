// Insights panel (M11): rule-based findings over live numbers. Grouped by urgency; each card can show the rule behind it.
import { Link } from "react-router-dom";
import { Loading, Panel, useGet } from "../components/ui.jsx";

const SECTIONS = [
  ["bad", "Needs action", "border-red-600", "text-red-700"],
  ["warning", "Keep an eye on", "border-amber-500", "text-amber-700"],
  ["neutral", "For information", "border-slate-400", "text-slate-700"],
  ["good", "Going well", "border-green-600", "text-green-700"],
];

export default function Insights() {
  const state = useGet("/api/reports/insights", { every: 60 });
  const d = state.data;
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold">Insights</h1>
      <p className="text-sm text-slate-600">Short findings worked out from the live numbers for your role. They point officers to where to look; they never decide anything. Open "How this was worked out" to see the rule.</p>
      <Loading state={state} />
      {d && d.insights.length === 0 && <Panel title="Nothing to flag"><div className="text-sm text-slate-500">{d.note}</div></Panel>}
      {d && d.insights.length > 0 && (
        <div className="flex flex-wrap gap-2 text-sm">
          {SECTIONS.map(([tone, label, , txt]) => {
            const n = d.insights.filter((i) => i.tone === tone).length;
            return n ? <span key={tone} className={"rounded border bg-white px-3 py-1 " + txt}><b>{n}</b> {label.toLowerCase()}</span> : null;
          })}
        </div>
      )}
      {d && SECTIONS.map(([tone, label, border, txt]) => {
        const items = d.insights.filter((i) => i.tone === tone);
        if (!items.length) return null;
        return (
          <section key={tone}>
            <h2 className={"mb-2 text-sm font-semibold uppercase tracking-wide " + txt}>{label}</h2>
            <div className="grid gap-3 lg:grid-cols-2">
              {items.map((i) => (
                <div key={i.id} className={"insight rounded border border-l-4 bg-white p-4 " + border}>
                  <div className="font-semibold text-slate-900">{i.title}</div>
                  <p className="mt-1 text-sm text-slate-700">{i.detail}</p>
                  <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                    <details className="text-xs text-slate-500">
                      <summary className="cursor-pointer">How this was worked out</summary>
                      <p className="mt-1 max-w-md">{i.rule}</p>
                    </details>
                    {i.link && <Link className="rounded border px-3 py-1 text-sm text-blue-700 hover:bg-slate-50" to={i.link}>Open →</Link>}
                  </div>
                </div>
              ))}
            </div>
          </section>
        );
      })}
      {d && <p className="text-xs text-slate-500">As of {d.as_of}. {d.note}</p>}
    </div>
  );
}
