import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { dbConfigured, getStoredSettings, putStoredSettings } from "@/lib/db";
import { canManage, fetchUserGuilds } from "@/lib/discord";
import { botAuthorized } from "@/lib/access";
import { SETTING_DEFAULTS, cleanValue } from "@/lib/settings";

async function userCanManage(guildId: string): Promise<boolean> {
  const session = await auth();
  const token = session?.accessToken;
  if (!token) return false;
  try {
    const guilds = await fetchUserGuilds(token);
    return guilds.some((g) => g.id === guildId && canManage(g));
  } catch {
    return false;
  }
}

export async function GET(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  if (!botAuthorized(req)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  if (!dbConfigured()) {
    return NextResponse.json({ error: "database_not_configured" }, { status: 503 });
  }
  const stored = await getStoredSettings(id);
  // Mentah tanpa merge default — bot menentukan default sendiri per key.
  return NextResponse.json({ guild_id: id, settings: stored });
}

export async function PUT(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  if (!(await userCanManage(id))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  if (!dbConfigured()) {
    return NextResponse.json({ error: "database_not_configured" }, { status: 503 });
  }
  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  const clean: Record<string, boolean | string | number> = {};
  for (const key of Object.keys(SETTING_DEFAULTS)) {
    const v = cleanValue(key, body[key]);
    if (v !== undefined) clean[key] = v;
  }
  const stored = await getStoredSettings(id);
  await putStoredSettings(id, { ...stored, ...clean });
  return NextResponse.json({ ok: true });
}
