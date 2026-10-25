// Placeholder card used by every page that is not built yet.
// future=true means later scope (stub); otherwise it is planned for the given module.
export default function ComingSoon({ title, module, future = false }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8">
      <h1 className="text-xl font-semibold text-slate-800">{title}</h1>
      <p className="mt-2 text-slate-600">
        Coming soon.{" "}
        {future ? "Future scope: kept as a stub for now." : `Planned for ${module}.`}
      </p>
    </div>
  );
}
