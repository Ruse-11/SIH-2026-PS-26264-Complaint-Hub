// Search box that suggests colleges while you type (same registry search the Institution Finder uses).
// Pick a suggestion -> onPick(card). Press Enter -> onSubmit(text) (plain search by name, AICTE ID or case ID).
import { useEffect, useRef, useState } from "react";
import { useAuth } from "../auth.jsx";

export default function InstitutionSuggest({ id, value, onChange, onPick, onSubmit, placeholder, className = "" }) {
  const [cards, setCards] = useState([]);
  const [open, setOpen] = useState(false);
  const { api } = useAuth();
  const timer = useRef(null);
  const current = useRef("");  // what is in the box right now
  current.current = (value || "").trim();

  useEffect(() => {
    clearTimeout(timer.current);
    const text = (value || "").trim();
    if (text.length < 2) { setCards([]); return; }
    timer.current = setTimeout(() => {  // wait until typing pauses, so we do not call the hub on every key
      api("/api/institutions/suggest?q=" + encodeURIComponent(text))
        .then((r) => (r.ok ? r.json() : []))
        .then((d) => { if (current.current === text) setCards(d); })  // ignore an answer for text that has since changed
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
          {cards.map((c) => (
            <li key={c.aicte_id}>
              <button type="button" className="block w-full px-3 py-2 text-left hover:bg-slate-100" onMouseDown={(e) => e.preventDefault()}
                onClick={() => { setOpen(false); onPick(c); }}>
                <span className="font-medium">{c.official_name}</span>
                <span className="block text-xs text-slate-500">{c.aicte_id} · {c.district}, {c.state}
                  {c.colleges > 0 ? ` · university, includes ${c.colleges} colleges` : c.parent_name ? ` · part of ${c.parent_name}` : ""}</span>
              </button>
            </li>
          ))}
          <li className="border-t bg-slate-50 px-3 py-1 text-xs text-slate-500">Press Enter to search all cases for “{(value || "").trim()}”</li>
        </ul>
      )}
    </div>
  );
}
