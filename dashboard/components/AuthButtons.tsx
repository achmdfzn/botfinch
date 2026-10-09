"use client";

import { signIn, signOut } from "next-auth/react";
import { useI18n } from "./I18nProvider";

export function SignInButton({ compact = false }: { compact?: boolean } = {}) {
  const { dict } = useI18n();
  return (
    <button
      onClick={() => signIn("discord", { callbackUrl: "/dashboard" })}
      className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-ink hover:bg-brand-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand min-h-[44px]"
    >
      {compact ? (
        <>
          {/* Label pendek di HP: "Masuk dengan Discord" terlalu panjang untuk header sempit */}
          <span className="sm:hidden">{dict.nav.signInShort}</span>
          <span className="hidden sm:inline">{dict.auth.signIn}</span>
        </>
      ) : (
        dict.auth.signIn
      )}
    </button>
  );
}

export function SignOutButton() {
  const { dict } = useI18n();
  return (
    <button
      onClick={() => signOut({ callbackUrl: "/" })}
      className="rounded-lg px-4 py-2 text-sm font-medium text-muted hover:bg-edge hover:text-fg focus-visible:outline-2 focus-visible:outline-brand min-h-[44px]"
    >
      {dict.auth.signOut}
    </button>
  );
}
