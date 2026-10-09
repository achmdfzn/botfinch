import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import I18nProvider from "@/components/I18nProvider";
import { getDict, getLang } from "@/lib/i18n";

const inter = Inter({ variable: "--font-sans", subsets: ["latin"] });

// Layout membaca cookie bahasa (getLang) -> render dinamis per request.
// `instant = false`: opt-out dari validasi instant navigation (bukan pengatur
// prerender — sifat dinamis dijamin oleh `await connection()` di tiap page).
export const instant = false;

// Anti-FOUC: pasang class 'light' SEBELUM paint pertama bila tersimpan di
// localStorage. Default = dark (identitas dasbor), jadi tanpa class = dark.
const THEME_SCRIPT =
  "(function(){try{if(localStorage.getItem('finch-theme')==='light'){document.documentElement.classList.add('light');}}catch(e){}})();";

export async function generateMetadata(): Promise<Metadata> {
  const dict = getDict(await getLang());
  return {
    title: dict.landing.metaTitle,
    description: dict.landing.metaDescription,
    icons: { icon: "/finch.png" },
  };
}

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const lang = await getLang();
  const dict = getDict(lang);
  return (
    // suppressHydrationWarning: script anti-FOUC boleh menambah class 'light'
    // sebelum React hydration tanpa dianggap mismatch.
    <html lang={lang} suppressHydrationWarning className={`${inter.variable} h-full antialiased`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-full bg-ink text-fg">
        <I18nProvider lang={lang} dict={dict}>
          {children}
        </I18nProvider>
      </body>
    </html>
  );
}
