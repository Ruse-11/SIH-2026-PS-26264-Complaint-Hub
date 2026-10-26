// Insights panel (M11): rule-based findings over live numbers. Every card shows the rule that produced it.
import { Link } from "react-router-dom";
import { Loading, Panel, useGet } from "../components/ui.jsx";

const TONE = {
  bad: "border-red-500 bg-red-50",
  warning: "border-amber-500 bg-amber-50",
  neutral: "border-slate-400 bg-white",
  good: "border-green-600 bg-green-50",
};
const TONE_LABEL = { bad: "Needs action", warning: "Watch", neutral: "For information", good: "Going well" };

export default function Insights() {
  const state = useGet("/api/reports/insights");
  const d = state.data;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Insights</h1>
      <p className="text-sm text-slate-600">Plain rules over the live numbers for your role. These are pointers for officers, not decisions.</p>
      <Loading state={state} />
      {d && d.insights.length === 0 && <Panel title="Nothing to flag"><div className="text-sm text-slate-500">{d.note}</div></Panel>}
      {d && (
        <div className="grid gap-4 lg:grid-cols-2">
          {d.insights.map((i) => (
            <div key={i.id} className={"insight rounded-xl border-l-4 p-4 shadow-sm " + (TONE[i.tone] || TONE.neutral)}>
              <div className="text-xs uppercase tracking-wide text-slate-500">{TONE_LABEL[i.tone] || i.tone}</div>
              <div className="mt-1 font-medium text-slate-900">{i.title}</div>
              <p className="mt-1 text-sm text-slate-700">{i.detail}</p>
              <p className="mt-2 text-xs text-slate-500">Rule: {i.rule}</p>
              {i.link && <Link className="mt-2 inline-block text-sm text-blue-700 hover:underline" to={i.link}>Open</Link>}
            </div>
          ))}
        </div>
      )}
      {d && <p className="text-xs text-slate-500">As of {d.as_of}. {d.note}</p>}
    </div>
  );
}
