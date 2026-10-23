import { withDbError } from "@/lib/db";
import { handleProviderWebhook } from "@/lib/payments/service";

/**
 * Webhook callback Xendit Invoice. Verifikasi header x-callback-token di
 * provider; token salah = 401 tanpa perubahan data. Lihat BILLING.md.
 */
export const POST = withDbError(async function POST(req: Request) {
  return handleProviderWebhook("xendit", req);
});
