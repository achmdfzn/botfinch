import { getDict, getLang } from "@/lib/i18n";

/** Skeleton daftar server; token tema agar benar di dark maupun light. */
export default async function Loading() {
  const dict = getDict(await getLang());
  return (
    <main className="mx-auto max-w-5xl px-4 py-10" aria-busy="true" aria-label={dict.loading.ariaLabel}>
      <div className="h-8 w-48 animate-pulse rounded-lg bg-edge" />
      <div className="mt-2 h-4 w-72 max-w-full animate-pulse rounded bg-edge" />
      <div className="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="h-20 animate-pulse rounded-xl border border-edge bg-panel" />
        ))}
      </div>
    </main>
  );
}
