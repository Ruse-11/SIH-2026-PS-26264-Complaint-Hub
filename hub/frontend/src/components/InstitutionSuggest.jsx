// Search box that suggests colleges while you type (same registry search the Institution Finder uses).
// Pick a suggestion -> onPick(card). Press Enter -> onSubmit(text) (plain search by name, AICTE ID or case ID).
import { useEffect, useRef, useState } from "react";

export default function InstitutionSuggest({ id, value, onChange, onPick, onSubmit, placeholder, className = "" }) {
  const [cards, setCards] = useState([]);
  const [open, setOpen] = useState(false);
  const [hint, setHint] = useState("");
  const timer = useRef(null);

  useEffect(() => {
    clearTimeout(timer.current);
    const text = (value || "").trim();
    if (text.length < 2) { setCards([]); setHint(""); return; }
    timer.current = setTimeout(() => {  // wait until typing pauses, so we do not call the hub on every key
      fetch("/api/institutions/search?q=" + encodeURIComponent(text))
        .then((r) => r.json())
        .then((d) => { setCards(d.candidates || []); setHint(d.outcome === "AMBIGUOUS" ? d.reason : ""); })
        .catch(() => setCards([]));
    }, 250);
    return () => clearTimeout(timer.current);
  }, [value]);

  return (
    <div className={"relative " + className}>
      <form onSubmit={(e) => { e.preventDefault(); setOpen(false); onSubmit && onSubmit((value || "").trim()); }}>
        <input id={id} autoComplete="off" value={value} placeholder={placeholder} className="w-full rounded border px-3 py-2 text-sm"
          onChange={(e) => { onChange(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)} />
      </form>
      {open && cards.length > 0 && (
        <ul className="absolute z-20 mt-1 w-full overflow-hidden rounded-lg border bg-white text-sm shadow-lg">
          {hint && <li className="bg-amber-50 px-3 py-1 text-xs text-amber-900">{hint}</li>}
          {cards.map((c) => (
            <li key={c.aicte_id}>
              <button type="button" className="block w-full px-3 py-2 text-left hover:bg-slate-100" onMouseDown={(e) => e.preventDefault()}
                onClick={() => { setOpen(false); onPick(c); }}>
                <span className="font-medium">{c.official_name}</span>
                <span className="block text-xs text-slate-500">{c.aicte_id} · {c.district}, {c.state} · show its cases</span>
              </button>
            </li>
          ))}
          <li className="border-t bg-slate-50 px-3 py-1 text-xs text-slate-500">Press Enter to search all cases for “{(value || "").trim()}”</li>
        </ul>
      )}
    </div>
  );
}
