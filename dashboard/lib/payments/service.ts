// lib/payments/service.ts — jalur TUNGGAL pemrosesan status pembayaran.
// Webhook provider dan rekonsiliasi (polling GET status saat halaman order
// dibuka) sama-sama lewat processProviderStatus, jadi tidak ada dua logika
// "apa yang terjadi saat order dibayar" yang bisa divergen.
//
// Idempotensi: entitlement hanya diterapkan oleh PEMENANG
// claimBillingOrderPaid (klaim atomik dibayar di DB). Event duplikat /
// balapan webhook + rekonsiliasi kalah klaim -> 'already_applied' dan
// applyPaymentToEntitlement TIDAK dipanggil lagi (durasi tidak ganda).
// Penanda klaim (paid_at) terpisah dari penanda penerapan
// (entitlement_applied_at): bila proses mati di antara klaim dan
// penerapan, order tertinggal 'paid' tanpa penanda penerapan dan jalur
// PEMULIHAN di bawah menerapkannya pada retry/rekonsiliasi berikutnya
// (dijaga atribusi provider_entitlement_id + umur klaim, lihat
// RECOVERY_AFTER_MS).
import { NextResponse } from "next/server";
import {
  applyPaymentToEntitlement,
  claimBillingOrderPaid,
  getBillingOrderByRef,
  getEntitlement,
  markBillingOrderApplied,
  recordWebhookEvent,
  revokeEntitlementForRefund,
  transitionBillingOrder,
  type BillingOrder,
} from "@/lib/db";
import { transitionSources, type PaymentProviderId } from "../billing";
import { getProviderById } from "./index";
import type { ProviderStatus } from "./types";

export interface ProcessOutcome {
  outcome: string;
}

const SETTLEMENT_BLOCKED_STATUSES: readonly string[] = [
  "failed",
  "cancelled",
  "refunded",
  "disputed",
];

/**
 * Klaim yang penerapannya terputus hanya dipulihkan setelah umur ini:
 * penerapan yang sedang berjalan normal selesai jauh lebih cepat, jadi
 * klaim yang lebih tua dari ini tanpa penanda penerapan hampir pasti
 * yatim (proses mati), bukan sedang berjalan.
 */
export const RECOVERY_AFTER_MS = 60_000;

export async function processProviderStatus(
  order: BillingOrder,
  status: ProviderStatus,
  opts: { source: "webhook" | "reconcile" },
): Promise<ProcessOutcome> {
  void opts; // sumber dicatat pemanggil (webhook event log); logika sama.
  const ref = order.order_ref;

  switch (status.kind) {
    case "paid": {
      // Nominal & mata uang WAJIB cocok persis dengan order. Apa pun yang
      // tidak bisa dipastikan (amountIdr undefined) ditolak — jangan pernah
      // mengaktifkan VIP dari payload yang nominalnya tidak terbukti.
      if (
        status.amountIdr == null ||
        status.amountIdr !== order.amount_idr ||
        (status.currency != null && status.currency !== "IDR")
      ) {
        return { outcome: "amount_mismatch" };
      }
      // Settlement yang datang setelah order terminal (gagal/batal/refund/
      // dispute) dicatat pemanggil tapi TIDAK diterapkan: uang pada order
      // yang sudah ditutup harus ditangani manual owner, bukan auto-VIP.
      // Pengecualian: 'expired' BUKAN pemblokir (late settlement, di bawah).
      if (SETTLEMENT_BLOCKED_STATUSES.includes(order.status)) {
        return { outcome: "settlement_after_terminal" };
      }
      const claim = await claimBillingOrderPaid(
        ref,
        status.providerTxnId ?? order.provider_txn_id,
      );
      if (claim) {
        // Klaim menang dari status 'expired' = pembeli membayar tepat di
        // batas waktu (late settlement): tetap dihormati, ditandai di note.
        const note = claim.previousStatus === "expired" ? "late_settlement" : undefined;
        const applied = await applyPaymentToEntitlement(
          order.guild_id,
          order.duration_days,
          order.provider,
          ref,
          note,
        );
        // Penanda penerapan di-set HANYA setelah apply berhasil — bila
        // proses mati sebelum baris ini, order tertinggal 'paid' tanpa
        // penanda dan jalur pemulihan di bawah yang menyelesaikan.
        await markBillingOrderApplied(ref, status.providerTxnId ?? order.provider_txn_id);
        return { outcome: `applied:${applied}` };
      }
      // Klaim kalah. Tiga kemungkinan: (a) penerapan sudah selesai ->
      // 'already_applied'; (b) klaim lain sedang menerapkan -> jangan
      // ganggu, jawab sama; (c) klaim sebelumnya MENANG tetapi proses
      // mati sebelum penerapan selesai -> PEMULIHAN: terapkan sekarang.
      // (c) dikenali dari: order 'paid', penanda penerapan masih NULL,
      // klaim sudah berumur > RECOVERY_AFTER_MS, dan entitlement belum
      // teratribusi ke order ini (provider_entitlement_id !== ref).
      const fresh = await getBillingOrderByRef(ref);
      if (fresh && fresh.status === "paid" && fresh.entitlement_applied_at === null) {
        const claimAgeMs =
          fresh.updated_at !== null
            ? Date.now() - new Date(fresh.updated_at).getTime()
            : Number.POSITIVE_INFINITY;
        if (claimAgeMs > RECOVERY_AFTER_MS) {
          const ent = await getEntitlement(fresh.guild_id);
          if (ent?.provider_entitlement_id === ref) {
            // Penerapan ternyata selesai; hanya penandanya yang hilang.
            await markBillingOrderApplied(ref, fresh.provider_txn_id);
            return { outcome: "recovered_marked" };
          }
          const applied = await applyPaymentToEntitlement(
            fresh.guild_id,
            fresh.duration_days,
            fresh.provider,
            ref,
            "recovery_after_claim",
          );
          await markBillingOrderApplied(ref, fresh.provider_txn_id);
          return { outcome: `recovered:${applied}` };
        }
      }
      return { outcome: "already_applied" };
    }
    case "pending": {
      const ok = await transitionBillingOrder(ref, "pending", transitionSources("pending"));
      return { outcome: ok ? "pending" : "ignored" };
    }
    case "failed":
    case "cancelled":
    case "expired": {
      const ok = await transitionBillingOrder(ref, status.kind, transitionSources(status.kind));
      return { outcome: ok ? "transitioned" : "ignored" };
    }
    case "refunded": {
      // Nominal refund yang dilaporkan provider harus cocok dengan order
      // bila tersedia — refund untuk nominal lain tidak mencabut apa pun.
      if (status.amountIdr != null && status.amountIdr !== order.amount_idr) {
        return { outcome: "amount_mismatch" };
      }
      const ok = await transitionBillingOrder(ref, "refunded", transitionSources("refunded"));
      if (!ok) return { outcome: "ignored" };
      await revokeEntitlementForRefund(
        order.guild_id,
        order.provider,
        ref,
        order.duration_days,
      );
      return { outcome: "refunded" };
    }
    case "disputed": {
      // Dispute/chargeback: order ditandai, entitlement SENGAJA tidak
      // diubah di sini — keputusan mencabut/membiarkan ada di owner
      // (review manual), karena dispute bisa dimenangkan merchant.
      const ok = await transitionBillingOrder(ref, "disputed", transitionSources("disputed"));
      return { outcome: ok ? "disputed" : "ignored" };
    }
    default:
      return { outcome: "ignored" };
  }
}

/**
 * Handler webhook bersama untuk semua provider.
 * Urutan keamanan: provider terkonfigurasi -> verifikasi signature/token
 * (gagal = 401, TANPA sentuhan data) -> catat event (dedup audit) ->
 * order ada (404) -> provider order cocok (400) -> proses status.
 * 'amount_mismatch' dijawab 400 agar provider me-retry & anomali terlihat;
 * 'settlement_after_terminal' dijawab 200 (sudah dicatat di webhook log).
 * Body/signature/secret TIDAK PERNAH di-log.
 */
export async function handleProviderWebhook(
  providerId: PaymentProviderId,
  req: Request,
): Promise<NextResponse> {
  const provider = getProviderById(providerId);
  if (!provider) {
    return NextResponse.json({ error: "provider_not_configured" }, { status: 503 });
  }
  const rawBody = await req.text();
  const ev = await provider.verifyWebhook(req.headers, rawBody);
  if (!ev) {
    return NextResponse.json({ error: "invalid_signature" }, { status: 401 });
  }
  await recordWebhookEvent(providerId, ev.eventKey, ev.orderRef, ev.status.rawStatus);
  const order = await getBillingOrderByRef(ev.orderRef);
  if (!order) {
    return NextResponse.json({ error: "order_not_found" }, { status: 404 });
  }
  if (order.provider !== providerId) {
    return NextResponse.json({ error: "provider_mismatch" }, { status: 400 });
  }
  // Midtrans: signature SHA512 notifikasi TIDAK mencakup
  // transaction_status / fraud_status — field yang justru menentukan
  // hasil. Payload notifikasi karena itu TIDAK dipercaya untuk
  // keputusan status: notifikasi hanya pemicu, status resmi diambil
  // dari API provider (fetchStatus) dan itulah yang diproses. Tanpa
  // langkah ini, satu signature sah milik notifikasi pending/challenge
  // yang bocor dapat diubah isinya menjadi settlement. (Xendit tidak
  // memerlukan ini: token callback mengautentikasi seluruh body.)
  let statusToProcess = ev.status;
  if (providerId === "midtrans") {
    try {
      statusToProcess = await provider.fetchStatus(
        order.order_ref,
        ev.providerTxnId || undefined,
      );
    } catch {
      // Provider tidak bisa dikonfirmasi sekarang: jawab 502 agar
      // Midtrans me-retry notifikasi, JANGAN memproses payload mentah.
      return NextResponse.json(
        { error: "provider_status_unavailable" },
        { status: 502 },
      );
    }
  }
  const { outcome } = await processProviderStatus(order, statusToProcess, {
    source: "webhook",
  });
  if (outcome === "amount_mismatch") {
    return NextResponse.json({ error: "amount_mismatch", outcome }, { status: 400 });
  }
  return NextResponse.json({ ok: true, outcome });
}
