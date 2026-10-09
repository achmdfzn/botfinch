export default function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-edge bg-panel p-5">
      <p className="text-3xl font-bold tracking-tight text-fg">{value}</p>
      <p className="mt-1 text-sm text-muted">{label}</p>
    </div>
  );
}
