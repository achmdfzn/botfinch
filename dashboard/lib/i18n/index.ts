// Entry point i18n untuk Server Component.
// getLang membaca cookie 'finch-lang' (server-only: next/headers).
// Client Component memakai "@/lib/i18n/client" + useI18n().
import { cookies } from "next/headers";

export { id, en, getDict, fmt } from "./dicts";
export type { Lang, Dict } from "./dicts";

export async function getLang(): Promise<"id" | "en"> {
  try {
    const v = (await cookies()).get("finch-lang")?.value;
    return v === "en" ? "en" : "id";
  } catch {
    return "id";
  }
}
