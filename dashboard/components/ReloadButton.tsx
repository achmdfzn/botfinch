"use client";

import { useRouter } from "next/navigation";
import { useI18n } from "@/components/I18nProvider";

/**
 * Tombol "coba lagi" untuk EmptyState error (mis. Discord tidak merespons).
 * router.refresh() memuat ulang server component tanpa reload penuh halaman.
 */
export default function ReloadButton() {
  const router = useRouter();
  const { dict } = useI18n();
  return (
    <button
      type="button"
      onClick={() => router.refresh()}
      className="rounded-lg bg-brand px-6 py-2.5 text-sm font-semibold text-ink hover:bg-brand-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand min-h-[44px]"
    >
      {dict.dashboard.retry}
    </button>
  );
}
