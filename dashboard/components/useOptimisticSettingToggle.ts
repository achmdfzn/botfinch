"use client";

import { useCallback, useRef, useState } from "react";

/**
 * Toggle setting on/off via PUT /api/guilds/[guildId]/settings dengan pola
 * optimistik + rollback (dipakai PluginCards dan ModuleToggles).
 *
 * - Guard inflight: abaikan toggle yang request-nya masih berjalan
 *   (race dua PUT bisa membalik rollback).
 * - State optimistik langsung diterapkan; bila request gagal, nilai
 *   dikembalikan (rollback) dan flag error dinyalakan.
 * - `onSuccess` dipanggil setelah PUT sukses (mis. router.refresh()).
 */
export function useOptimisticSettingToggle(
  guildId: string,
  initial: Record<string, boolean>,
  onSuccess?: () => void,
) {
  const [values, setValues] = useState<Record<string, boolean>>(initial);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<boolean>(false);
  // Guard klik ganda: abaikan toggle yang request-nya masih berjalan
  // (optimistik + rollback; race dua PUT bisa membalik rollback).
  const inflight = useRef(new Set<string>());

  const toggle = useCallback(
    async (key: string, v: boolean) => {
      if (inflight.current.has(key)) return;
      inflight.current.add(key);
      setError(false);
      setSaving(key);
      setValues((prev) => ({ ...prev, [key]: v }));
      try {
        const res = await fetch(`/api/guilds/${guildId}/settings`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ [key]: v }),
        });
        if (!res.ok) throw new Error("http");
        onSuccess?.();
      } catch {
        setValues((prev) => ({ ...prev, [key]: !v }));
        setError(true);
      } finally {
        inflight.current.delete(key);
        setSaving(null);
      }
    },
    [guildId, onSuccess],
  );

  return { values, saving, error, toggle };
}
