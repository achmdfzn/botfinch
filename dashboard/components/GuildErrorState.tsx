import EmptyState from "@/components/EmptyState";
import ReloadButton from "@/components/ReloadButton";

/**
 * C-001: status error DB-bel dikonfigurasi untuk halaman per-server.
 * Sengaja TANPA <SiteHeader> dan TANPA <main>: komponen ini dipakai di
 * dalam layout dashboard per-server (DashboardShell) yang sudah punya
 * chrome-nya sendiri. Wrapper menyamai pola lama (rata tengah, lebar baca
 * 3xl) tanpa menduplikasi header/main.
 *
 * retry: tampilkan tombol "Muat ulang" bila kondisi errornya mungkin
 *        sembuh dengan me-render ulang (default: tidak, sesuai cabang
 *        dbConfigured lama yang tidak punya tombol).
 */
export default function GuildErrorState({
  title,
  body,
  retry = false,
}: {
  title: string;
  body: string;
  retry?: boolean;
}) {
  return (
    <div className="mx-auto max-w-3xl px-4 py-16">
      <EmptyState
        title={title}
        body={body}
        action={retry ? <ReloadButton /> : undefined}
      />
    </div>
  );
}
