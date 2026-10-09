import Image from "next/image";
import Link from "next/link";
import { auth } from "@/auth";
import { inviteUrl } from "@/lib/discord";
import { getDict, getLang } from "@/lib/i18n";
import { SignInButton, SignOutButton } from "./AuthButtons";
import ThemeToggle from "./ThemeToggle";
import LangSwitcher from "./LangSwitcher";

// Contoh referensi tema + i18n untuk worker lain:
// - Server Component: getLang() (cookie) + getDict(lang)
// - Token semantik (text-fg, text-muted, bg-panel, border-edge, ...)
// - Kontrol client (ThemeToggle, LangSwitcher) hidup dari useI18n()
export default async function SiteHeader() {
  const session = await auth();
  const dict = getDict(await getLang());
  return (
    <header className="border-b border-edge bg-panel/80 sticky top-0 z-10 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4">
        <Link href="/" className="flex items-center gap-3 rounded-lg focus-visible:outline-2 focus-visible:outline-brand">
          <Image src="/finch.png" alt={dict.nav.logoAlt} width={36} height={36} className="rounded-full" />
          <span className="text-lg font-bold tracking-tight">Finch</span>
        </Link>
        <nav className="flex items-center gap-2">
          {session ? (
            <>
              <Link
                href="/dashboard"
                className="rounded-lg px-4 py-2 text-sm font-medium text-muted hover:bg-edge hover:text-fg focus-visible:outline-2 focus-visible:outline-brand"
              >
                {dict.nav.myServers}
              </Link>
              <SignOutButton />
            </>
          ) : (
            <>
              <a
                href={inviteUrl()}
                className="rounded-lg px-4 py-2 text-sm font-medium text-muted hover:bg-edge hover:text-fg focus-visible:outline-2 focus-visible:outline-brand"
              >
                {dict.nav.inviteBot}
              </a>
              <SignInButton />
            </>
          )}
          <ThemeToggle />
          <LangSwitcher />
        </nav>
      </div>
    </header>
  );
}
