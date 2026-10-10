"use client";

import { useEffect } from "react";
import { useI18n } from "@/components/I18nProvider";
import EmptyState from "@/components/EmptyState";

/**
 * A-012: jaring pengaman error tak terduga untuk seluruh segmen /dashboard.
 * Error boundary Next.js: menangkap error render di halaman dashboard dan
 * segmen turunannya, lalu reset() mencoba me-render ulang segmen tanpa
 * reload penuh halaman. Teks diambil dari I18nProvider (root layout)
 * sehingga tetap bilingual ID/EN; key kamus i18n tidak ditambah.
 */
export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { dict } = useI18n();

  useEffect(() => {
    // Detail teknis hanya di console untuk diagnosa; pengguna hanya
    // melihat judul/body umum dan tombol coba lagi.
    console.error("[dashboard] error boundary:", error);
  }, [error]);

  return (
    <div className="mx-auto max-w-3xl px-4 py-16">
      <EmptyState
        title={dict.guild.common.loadTitle}
        body={dict.guild.common.loadBody}
        action={
          <button
            type="button"
            onClick={() => reset()}
            className="min-h-[44px] rounded-lg bg-brand px-6 py-2.5 text-sm font-semibold text-ink hover:bg-brand-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            {dict.dashboard.retry}
          </button>
        }
      />
    </div>
  );
}
