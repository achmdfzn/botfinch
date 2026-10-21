#!/usr/bin/env python3
"""Apply a guarded first-pass fix set to an achmdfzn/botfinch checkout.

Run from the repository root:
    python apply_botfinch_audit_fixes.py --check
    python apply_botfinch_audit_fixes.py

The script validates every expected source anchor before writing any file. On
apply, originals are backed up under .botfinch-audit-backup/ first.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path.cwd()


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one anchor for {label}, found {count}")
    return source.replace(old, new, 1)


def replace_range(source: str, start: str, end: str, new: str, label: str) -> str:
    a = source.find(start)
    b = source.find(end, a + len(start)) if a >= 0 else -1
    if a < 0 or b < 0:
        raise RuntimeError(f"Could not locate start/end anchors for {label}")
    return source[:a] + new + source[b:]


def read_repo_file(path: str) -> str:
    file = ROOT / path
    if not file.is_file():
        raise RuntimeError(f"Run this from the Botfinch repository root; missing {path}")
    return file.read_text(encoding="utf-8")


def build_changes() -> dict[str, str]:
    changed: dict[str, str] = {}

    # Bot: fail-closed channel ownership checks and durable announcement status.
    path = "bot/src/cogs/dashboard_sync.py"
    s = read_repo_file(path)
    s = replace_once(
        s,
        '''def _int_aman(nilai, default: int = 0) -> int:
    """int() yang tidak pernah raise — untuk id dari payload dashboard."""
    try:
        return int(nilai)
    except (ValueError, TypeError):
        return default''',
        '''def _int_aman(nilai, default: int = 0) -> int:
    """int() yang tidak pernah raise — untuk id dari payload dashboard."""
    try:
        return int(nilai)
    except (ValueError, TypeError):
        return default


def _channel_milik_guild(channel, guild_id: int) -> bool:
    """Fail-closed: channel tujuan harus benar-benar milik guild yang diproses."""
    guild = getattr(channel, "guild", None)
    return guild is not None and getattr(guild, "id", None) == guild_id''',
        "channel ownership helper",
    )
    s = replace_once(
        s,
        '''                channel = guild.get_channel(int(r["channel_id"])) or await self.bot.fetch_channel(int(r["channel_id"]))
                detik = max(60, int(r["duration_minutes"]) * 60)''',
        '''                channel = guild.get_channel(int(r["channel_id"])) or await self.bot.fetch_channel(int(r["channel_id"]))
                if not _channel_milik_guild(channel, guild.id):
                    await self._ack_giveaway(
                        guild.id, req_id, "failed", "channel bukan milik server ini"
                    )
                    continue
                detik = max(60, int(r["duration_minutes"]) * 60)''',
        "giveaway destination ownership guard",
    )
    s = replace_once(
        s,
        '''            if channel is None:
                await self._ack_embed(guild.id, req_id, "failed", "channel tidak ditemukan")
                continue
            try:
                embed = _bangun_embed(r)''',
        '''            if channel is None:
                await self._ack_embed(guild.id, req_id, "failed", "channel tidak ditemukan")
                continue
            if not _channel_milik_guild(channel, guild.id):
                await self._ack_embed(
                    guild.id, req_id, "failed", "channel bukan milik server ini"
                )
                continue
            try:
                embed = _bangun_embed(r)''',
        "embed destination ownership guard",
    )

    new_announcement_methods = '''    def _simpan_pengumuman(self, guild_id: int, rows: list) -> None:
        """Mirror pengumuman dashboard tanpa menimpa timestamp kirim yang lebih baru.

        Dashboard adalah sumber konfigurasi. Timestamp lokal yang lebih baru
        dipertahankan sampai acknowledgment sukses diselaraskan kembali.
        """
        with get_connection() as conn:
            status_lokal = {
                int(r[0]): r[1]
                for r in conn.execute(
                    "SELECT id, last_sent_at FROM dashboard_announcements WHERE guild_id = ?",
                    (str(guild_id),),
                ).fetchall()
            }
            conn.execute("DELETE FROM dashboard_announcements WHERE guild_id = ?", (str(guild_id),))
            for r in (rows or [])[:50]:
                try:
                    pesan = str(r["message"]).strip()
                    if not pesan:
                        continue
                    run_at = parse_iso(str(r.get("run_at") or "") or None)
                    terakhir_remote = parse_iso(str(r.get("last_sent_at") or "") or None)
                    terakhir_lokal = parse_iso(status_lokal.get(_int_aman(r.get("id"))))
                    terakhir = terakhir_remote
                    if terakhir_lokal is not None and (
                        terakhir_remote is None or terakhir_lokal > terakhir_remote
                    ):
                        terakhir = terakhir_lokal
                    interval = r.get("interval_minutes")
                    interval = _int_aman(interval) if interval is not None else None
                    conn.execute(
                        "INSERT INTO dashboard_announcements"
                        " (id, guild_id, channel_id, message, run_at, interval_minutes, enabled, last_sent_at)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            _int_aman(r["id"]),
                            str(guild_id),
                            str(r["channel_id"]),
                            pesan[:2000],
                            run_at.isoformat() if run_at else None,
                            interval,
                            1 if r.get("enabled", True) else 0,
                            terakhir.isoformat() if terakhir else None,
                        ),
                    )
                except (KeyError, TypeError):
                    continue
            conn.commit()

    async def _ack_announcement(
        self, guild_id: int, ann_id: int, last_sent_at: str
    ) -> bool:
        """Simpan waktu kirim di dashboard; False berarti perlu direkonsiliasi lagi."""
        try:
            async with aiohttp.ClientSession() as sesi:
                async with sesi.post(
                    f"{config.settings.dashboard_url}/api/guilds/{guild_id}/announcements/{ann_id}",
                    json={"last_sent_at": last_sent_at},
                    headers=self._headers(),
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status == 200:
                        return True
                    log.warning(
                        "dashboard: acknowledgment pengumuman %s ditolak (HTTP %d)",
                        ann_id, resp.status,
                    )
        except Exception:
            log.warning(
                "dashboard: gagal ack pengumuman %s", ann_id, exc_info=True
            )
        return False

    async def _rekonsiliasi_pengumuman(self, guild_id: int, rows: list) -> None:
        """Kirim ulang acknowledgment lokal yang lebih baru daripada snapshot server."""
        with get_connection() as conn:
            lokal = {
                int(r[0]): r[1]
                for r in conn.execute(
                    "SELECT id, last_sent_at FROM dashboard_announcements WHERE guild_id = ?",
                    (str(guild_id),),
                ).fetchall()
            }
        for row in (rows or [])[:50]:
            ann_id = _int_aman(row.get("id"))
            waktu_lokal = parse_iso(lokal.get(ann_id))
            waktu_remote = parse_iso(str(row.get("last_sent_at") or "") or None)
            if waktu_lokal is not None and (
                waktu_remote is None or waktu_lokal > waktu_remote
            ):
                await self._ack_announcement(guild_id, ann_id, waktu_lokal.isoformat())

'''
    s = replace_range(
        s,
        "    def _simpan_pengumuman(self, guild_id: int, rows: list) -> None:",
        "    async def _proses_giveaway",
        new_announcement_methods,
        "announcement persistence and retry methods",
    )
    s = replace_once(
        s,
        '''                self._simpan_pengumuman(g.id, data.get("announcements") or [])''',
        '''                pengumuman = data.get("announcements") or []
                await self._rekonsiliasi_pengumuman(g.id, pengumuman)
                self._simpan_pengumuman(g.id, pengumuman)''',
        "announcement pull reconciliation",
    )
    s = replace_once(
        s,
        '''        try:
            # Substitusi placeholder {server} / {date} / {member_count}
            teks = substitusi_pengumuman(
                pesan, guild.name, now, guild.member_count or 0
            )
            # Pengumuman ditulis admin via dashboard -> boleh @everyone.
            await channel.send(teks, allowed_mentions=MENTIONS_PENGUMUMAN)
        except Exception:
            return  # gagal -> lewati diam-diam
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE dashboard_announcements SET last_sent_at = ? WHERE id = ?",
                    (now.isoformat(), ann_id),
                )
                conn.commit()
        except Exception:
            log.warning("dashboard: gagal update last_sent_at pengumuman %s", ann_id, exc_info=True)''',
        '''        if not _channel_milik_guild(channel, guild.id):
            log.warning(
                "dashboard: pengumuman %s ditolak karena channel bukan milik guild %s",
                ann_id, guild.id,
            )
            return
        try:
            # Substitusi placeholder {server} / {date} / {member_count}
            teks = substitusi_pengumuman(
                pesan, guild.name, now, guild.member_count or 0
            )
            # Pengumuman ditulis admin via dashboard -> boleh @everyone.
            await channel.send(teks, allowed_mentions=MENTIONS_PENGUMUMAN)
        except Exception:
            return  # gagal -> lewati diam-diam
        waktu_kirim = discord.utils.utcnow().isoformat()
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE dashboard_announcements SET last_sent_at = ? WHERE id = ?",
                    (waktu_kirim, ann_id),
                )
                conn.commit()
        except Exception:
            log.warning("dashboard: gagal update last_sent_at pengumuman %s", ann_id, exc_info=True)
        # Lokal ditulis terlebih dahulu. Jika jaringan gagal, pull berikutnya
        # mempertahankan timestamp lokal dan mencoba menyelaraskannya ke server.
        await self._ack_announcement(_int_aman(gid_s), ann_id, waktu_kirim)''',
        "announcement send acknowledgment",
    )
    changed[path] = s

    # Bot core: welcome and goodbye must not send to a channel from another guild.
    path = "bot/src/bot.py"
    s = read_repo_file(path)
    s = replace_once(
        s,
        '''        channel_id = get_guild_setting_int(member.guild.id, "goodbye_channel_id", 0)
        channel = self.get_channel(channel_id) if channel_id else None
        if channel is None:''',
        '''        channel_id = get_guild_setting_int(member.guild.id, "goodbye_channel_id", 0)
        channel = self.get_channel(channel_id) if channel_id else None
        if channel is not None and getattr(getattr(channel, "guild", None), "id", None) != member.guild.id:
            log.warning(
                "Goodbye channel %s bukan milik guild %s; memakai system channel jika tersedia.",
                channel_id, member.guild.id,
            )
            channel = None
        if channel is None:''',
        "goodbye channel ownership guard",
    )
    s = replace_once(
        s,
        '''        channel = self.get_channel(channel_id) if channel_id else None
        if channel is None:
            # fallback: pakai system channel server
            channel = member.guild.system_channel
        if channel is None:
            return
        try:
            avatar_bytes = await member.display_avatar.read()''',
        '''        channel = self.get_channel(channel_id) if channel_id else None
        if channel is not None and getattr(getattr(channel, "guild", None), "id", None) != gid:
            log.warning(
                "Welcome channel %s bukan milik guild %s; memakai system channel jika tersedia.",
                channel_id, gid,
            )
            channel = None
        if channel is None:
            # fallback: pakai system channel server
            channel = member.guild.system_channel
        if channel is None:
            return
        try:
            avatar_bytes = await member.display_avatar.read()''',
        "welcome channel ownership guard",
    )
    changed[path] = s

    # Auto-slowmode should restore the previous value, not force slowmode to zero.
    path = "bot/src/cogs/moderation.py"
    s = read_repo_file(path)
    s = replace_once(
        s,
        '''        if delay >= 10:
            return
        try:
            await ch.edit(slowmode_delay=10, reason="Slowmode otomatis: chat terlalu ramai")''',
        '''        if delay >= 10:
            return
        delay_sebelumnya = delay
        try:
            await ch.edit(slowmode_delay=10, reason="Slowmode otomatis: chat terlalu ramai")''',
        "capture previous slowmode",
    )
    s = replace_once(
        s,
        '''        async def _kembalikan():
            await asyncio.sleep(300)
            try:
                await ch.edit(slowmode_delay=0, reason="Slowmode otomatis selesai")''',
        '''        async def _kembalikan():
            await asyncio.sleep(300)
            try:
                # Jangan menimpa perubahan admin selama masa auto-slowmode.
                # Pulihkan nilai sebelumnya hanya jika nilai masih 10 detik
                # yang dipasang oleh task ini.
                if (ch.slowmode_delay or 0) == 10:
                    await ch.edit(
                        slowmode_delay=delay_sebelumnya,
                        reason="Slowmode otomatis selesai",
                    )''',
        "restore previous slowmode safely",
    )
    changed[path] = s

    # Dashboard database helpers.
    path = "dashboard/lib/db.ts"
    s = read_repo_file(path)
    s = replace_once(
        s,
        '''export async function latestSnapshot(): Promise<SnapshotPayload | null> {
  if (!dbConfigured()) return null;
  const { rows } = await sql`SELECT payload FROM snapshots ORDER BY id DESC LIMIT 1`;
  return (rows[0]?.payload as SnapshotPayload) ?? null;
}''',
        '''export async function latestSnapshot(): Promise<SnapshotPayload | null> {
  if (!dbConfigured()) return null;
  const { rows } = await sql`SELECT payload FROM snapshots ORDER BY id DESC LIMIT 1`;
  return (rows[0]?.payload as SnapshotPayload) ?? null;
}

/** Cari channel pada snapshot terbaru dan batasi pencarian ke guild yang diminta. */
export async function getSnapshotChannel(
  guildId: string,
  channelId: string,
): Promise<SnapshotChannel | null> {
  const snapshot = await latestSnapshot();
  const guild = snapshot?.guilds.find((item) => item.id === guildId);
  return guild?.channels.find((channel) => channel.id === channelId) ?? null;
}''',
        "snapshot channel helper",
    )
    s = replace_once(
        s,
        '''export async function updateAnnouncement(
  id: number,
  guildId: string,
  patch: AnnouncementPatch,
): Promise<void> {''',
        '''/** Catat waktu pengiriman dari bot hanya untuk pengumuman milik guild yang sama. */
export async function markAnnouncementSent(
  id: number,
  guildId: string,
  lastSentAt: string,
): Promise<boolean> {
  const { rows } = await sql`
    UPDATE announcements
    SET last_sent_at = GREATEST(
      COALESCE(last_sent_at, ${lastSentAt}::timestamptz),
      ${lastSentAt}::timestamptz
    )
    WHERE id = ${id} AND guild_id = ${guildId}
    RETURNING id
  `;
  return rows.length > 0;
}

export async function updateAnnouncement(
  id: number,
  guildId: string,
  patch: AnnouncementPatch,
): Promise<void> {''',
        "announcement acknowledgement database method",
    )
    changed[path] = s

    # Dashboard APIs: validate channel ownership against the latest bot snapshot.
    path = "dashboard/app/api/guilds/[id]/announcements/route.ts"
    s = read_repo_file(path)
    s = replace_once(
        s,
        'import { createAnnouncement, listAnnouncements, withDbError } from "@/lib/db";',
        'import { createAnnouncement, getSnapshotChannel, listAnnouncements, withDbError } from "@/lib/db";',
        "announcement route import",
    )
    s = replace_once(
        s,
        "  const annId = await createAnnouncement({",
        '''  const target = await getSnapshotChannel(id, channelId);
  if (!target || (target.type !== 0 && target.type !== 5)) {
    return NextResponse.json({ error: "channel_not_in_guild_or_not_text" }, { status: 400 });
  }
  const annId = await createAnnouncement({''',
        "announcement POST channel validation",
    )
    changed[path] = s

    path = "dashboard/app/api/guilds/[id]/announcements/[annId]/route.ts"
    s = read_repo_file(path)
    s = replace_once(
        s,
        '''import {
  deleteAnnouncement,
  updateAnnouncement,
  type AnnouncementPatch, withDbError } from "@/lib/db";
import { requireManager } from "@/lib/access";''',
        '''import {
  dbConfigured,
  deleteAnnouncement,
  getSnapshotChannel,
  markAnnouncementSent,
  updateAnnouncement,
  type AnnouncementPatch,
  withDbError,
} from "@/lib/db";
import { botAuthorized, requireManager } from "@/lib/access";''',
        "announcement item route imports",
    )
    s = replace_once(
        s,
        "    patch.channelId = channelId;",
        '''    const target = await getSnapshotChannel(id, channelId);
    if (!target || (target.type !== 0 && target.type !== 5)) {
      return NextResponse.json({ error: "channel_not_in_guild_or_not_text" }, { status: 400 });
    }
    patch.channelId = channelId;''',
        "announcement PUT channel validation",
    )
    s = replace_once(
        s,
        '''export const PUT = withDbError(putImpl);
export const DELETE = withDbError(deleteImpl);''',
        '''/** Bot menandai jadwal terkirim menggunakan shared DASHBOARD_SECRET. */
async function postAckImpl(
  req: Request,
  { params }: { params: Promise<{ id: string; annId: string }> },
) {
  const { id, annId } = await params;
  if (!botAuthorized(req)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  if (!dbConfigured()) {
    return NextResponse.json({ error: "database_not_configured" }, { status: 503 });
  }
  if (invalidId(annId)) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  const body = await parseJsonBody(req);
  if (!body) return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  const lastSentAt = isoDateTime(body.last_sent_at);
  if (typeof lastSentAt !== "string") {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  const updated = await markAnnouncementSent(Number(annId), id, lastSentAt);
  if (!updated) return NextResponse.json({ error: "announcement_not_found" }, { status: 404 });
  return NextResponse.json({ ok: true });
}

export const PUT = withDbError(putImpl);
export const DELETE = withDbError(deleteImpl);
export const POST = withDbError(postAckImpl);''',
        "announcement POST acknowledgement",
    )
    changed[path] = s

    path = "dashboard/app/api/guilds/[id]/embed-requests/route.ts"
    s = read_repo_file(path)
    s = replace_once(
        s,
        'import { createEmbedRequest, listEmbedRequests, withDbError } from "@/lib/db";',
        'import { createEmbedRequest, getSnapshotChannel, listEmbedRequests, withDbError } from "@/lib/db";',
        "embed route import",
    )
    s = replace_once(
        s,
        "  const reqId = await createEmbedRequest({",
        '''  const target = await getSnapshotChannel(id, channelId);
  if (!target || (target.type !== 0 && target.type !== 5)) {
    return NextResponse.json({ error: "channel_not_in_guild_or_not_text" }, { status: 400 });
  }
  const reqId = await createEmbedRequest({''',
        "embed POST channel validation",
    )
    changed[path] = s

    path = "dashboard/app/api/guilds/[id]/giveaways/route.ts"
    s = read_repo_file(path)
    s = replace_once(
        s,
        'import { addGiveawayRequest, getGiveawayRequests, latestSnapshot, withDbError } from "@/lib/db";',
        'import { addGiveawayRequest, getGiveawayRequests, getSnapshotChannel, latestSnapshot, withDbError } from "@/lib/db";',
        "giveaway route import",
    )
    s = replace_once(
        s,
        "  await addGiveawayRequest(id, channelId, prize, winners, duration);",
        '''  const target = await getSnapshotChannel(id, channelId);
  if (!target || (target.type !== 0 && target.type !== 5)) {
    return NextResponse.json({ error: "channel_not_in_guild_or_not_text" }, { status: 400 });
  }
  await addGiveawayRequest(id, channelId, prize, winners, duration);''',
        "giveaway POST channel validation",
    )
    changed[path] = s

    # Per-guild channel and role settings must belong to the selected guild.
    path = "dashboard/app/api/guilds/[id]/settings/route.ts"
    s = read_repo_file(path)
    s = replace_once(
        s,
        'import { dbConfigured, getStoredSettings, mergeStoredSettings, withDbError } from "@/lib/db";',
        'import { dbConfigured, getStoredSettings, latestSnapshot, mergeStoredSettings, withDbError } from "@/lib/db";',
        "settings route import",
    )
    s = replace_once(
        s,
        '''  // Validasi lintas-key (D-003): /kerja minimal tidak boleh melebihi
  // maksimalnya. Dicek terhadap gabungan nilai tersimpan + request ini,
  // agar konfigurasi "terlihat salah" tidak tersimpan diam-diam.
  const efektif = { ...mergeSettings(await getStoredSettings(id)), ...clean };''',
        '''  // Validasi konfigurasi channel dan role terhadap snapshot guild tujuan.
  // Bot tetap memeriksa kepemilikan guild aktual sebelum menjalankan aksi.
  const snapshot = await latestSnapshot();
  const guildSnapshot = snapshot?.guilds.find((guild) => guild.id === id);
  const channelTypes = new Map(
    (guildSnapshot?.channels ?? []).map((channel) => [channel.id, channel.type] as const),
  );
  const roleIds = new Set((guildSnapshot?.roles ?? []).map((role) => role.id));
  for (const [key, value] of Object.entries(clean)) {
    if (typeof value !== "string" || value === "") continue;
    if (
      key.endsWith("_channel_id") ||
      key.endsWith("_category_id") ||
      key.endsWith("_lobby_id")
    ) {
      const type = channelTypes.get(value);
      const allowed = key.endsWith("_category_id")
        ? type === 4
        : key.endsWith("_lobby_id")
          ? type === 2
          : type === 0 || type === 5;
      if (!allowed) {
        return NextResponse.json(
          { error: "invalid_channel_setting", field: key },
          { status: 400 },
        );
      }
    }
    if (key === "welcome_role_ids") {
      const ids = value.split(",").map((item) => item.trim()).filter(Boolean);
      if (ids.some((roleId) => !roleIds.has(roleId))) {
        return NextResponse.json(
          { error: "invalid_role_setting", field: key },
          { status: 400 },
        );
      }
    }
    if (key === "leveling_roles") {
      let roles: unknown;
      try {
        roles = JSON.parse(value);
      } catch {
        return NextResponse.json(
          { error: "invalid_role_setting", field: key },
          { status: 400 },
        );
      }
      if (
        !Array.isArray(roles) ||
        roles.some((role) => {
          if (!role || typeof role !== "object" || Array.isArray(role)) return true;
          const roleId = (role as Record<string, unknown>).role_id;
          return typeof roleId !== "string" || !roleIds.has(roleId);
        })
      ) {
        return NextResponse.json(
          { error: "invalid_role_setting", field: key },
          { status: 400 },
        );
      }
    }
  }
  // Validasi lintas-key (D-003): /kerja minimal tidak boleh melebihi
  // maksimalnya. Dicek terhadap gabungan nilai tersimpan + request ini,
  // agar konfigurasi "terlihat salah" tidak tersimpan diam-diam.
  const efektif = { ...mergeSettings(await getStoredSettings(id)), ...clean };''',
        "settings channel/role guild validation",
    )
    changed[path] = s

    # Regression tests for the two new invariants.
    test_path = "bot/tests/test_audit5_boundaries.py"
    test_file = ROOT / test_path
    if test_file.exists():
        raise RuntimeError(f"Refusing to overwrite existing {test_path}")
    changed[test_path] = '''"""Regresi audit tahap 5: isolasi guild dan timestamp scheduler."""
from types import SimpleNamespace

from src import store
from src.cogs import dashboard_sync as ds


def test_channel_milik_guild_menerima_guild_yang_sama():
    channel = SimpleNamespace(guild=SimpleNamespace(id=12345))
    assert ds._channel_milik_guild(channel, 12345)


def test_channel_milik_guild_menolak_guild_lain_dan_dm():
    channel_lain = SimpleNamespace(guild=SimpleNamespace(id=54321))
    channel_dm = SimpleNamespace()
    assert not ds._channel_milik_guild(channel_lain, 12345)
    assert not ds._channel_milik_guild(channel_dm, 12345)
    assert not ds._channel_milik_guild(None, 12345)


def test_simpan_pengumuman_mempertahankan_timestamp_lokal_yang_lebih_baru(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "finch.db")
    store.init_db()
    guild_id = 12345
    timestamp_lokal = "2026-10-21T10:00:00+00:00"
    with store.get_connection() as conn:
        conn.execute(ds.TABEL_ANNOUNCEMENTS)
        conn.execute(
            "INSERT INTO dashboard_announcements "
            "(id, guild_id, channel_id, message, run_at, interval_minutes, enabled, last_sent_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (9, str(guild_id), "123456789", "pesan lama", None, 60, 1, timestamp_lokal),
        )
        conn.commit()

    cog = ds.DashboardSync.__new__(ds.DashboardSync)
    cog._simpan_pengumuman(
        guild_id,
        [{
            "id": 9,
            "channel_id": "123456789",
            "message": "pesan baru",
            "run_at": None,
            "interval_minutes": 60,
            "enabled": True,
            "last_sent_at": None,
        }],
    )

    with store.get_connection() as conn:
        row = conn.execute(
            "SELECT message, last_sent_at FROM dashboard_announcements WHERE id = ?",
            (9,),
        ).fetchone()
    assert row[0] == "pesan baru"
    assert row[1] == timestamp_lokal
'''

    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate anchors without writing files")
    args = parser.parse_args()

    # Build every replacement in memory first. No file is changed if an anchor mismatches.
    changes = build_changes()
    print("Validated patch targets:")
    for path in changes:
        print(f"  - {path}")
    if args.check:
        print("Check only: no files changed.")
        return

    backup_root = ROOT / ".botfinch-audit-backup" / datetime.now().strftime("%Y%m%d-%H%M%S")
    for path in changes:
        target = ROOT / path
        if target.exists():
            backup = backup_root / path
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
    for path, content in changes.items():
        target = ROOT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
    print(f"Applied {len(changes)} file changes.")
    print(f"Backups saved to: {backup_root}")
    print("Run the Python and dashboard test commands from the project README before deployment.")


if __name__ == "__main__":
    main()
