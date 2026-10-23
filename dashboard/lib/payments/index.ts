// lib/payments/index.ts — resolusi provider dari id / env aktif.
// Instance hanya dibuat bila credential provider itu lengkap di env;
// selain itu null (pemanggil menjawab 503 billing/provider not configured).
import { getActiveProviderId, type PaymentProviderId } from "../billing";
import { createMidtransProvider } from "./midtrans";
import { createXenditProvider } from "./xendit";
import type { PaymentProvider } from "./types";

export type { PaymentProvider, ProviderStatus, VerifiedEvent } from "./types";

export function getProviderById(id: string | null | undefined): PaymentProvider | null {
  if (id === "midtrans") return createMidtransProvider();
  if (id === "xendit") return createXenditProvider();
  return null;
}

export function getActiveProvider(): PaymentProvider | null {
  const id: PaymentProviderId | null = getActiveProviderId();
  return id ? getProviderById(id) : null;
}
