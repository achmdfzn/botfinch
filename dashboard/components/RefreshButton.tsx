"use client";

import { useRouter } from "next/navigation";

export default function RefreshButton() {
  const router = useRouter();
  return (
    <button
      onClick={() => router.refresh()}
      className="rounded-lg border border-edge px-4 py-2.5 text-sm font-medium text-zinc-300 hover:bg-edge focus-visible:outline-2 focus-visible:outline-brand min-h-[44px]"
    >
      Muat ulang
    </button>
  );
}
