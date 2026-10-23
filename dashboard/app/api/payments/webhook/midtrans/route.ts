import { withDbError } from "@/lib/db";
import { handleProviderWebhook } from "@/lib/payments/service";

/**
 * Webhook notifikasi Midtrans. Verifikasi signature SHA512 di provider;
 * signature salah = 401 tanpa perubahan data. Lihat BILLING.md.
 */
export const POST = withDbError(async function POST(req: Request) {
  return handleProviderWebhook("midtrans", req);
});
