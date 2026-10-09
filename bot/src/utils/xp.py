"""Logika terpusat untuk tambah XP dan handle level up.

Rumus: butuh level * 150 XP untuk naik level.
"""

import logging
import sqlite3
import discord

log = logging.getLogger("finch")

async def beri_role_reward(member: discord.Member, level: int) -> None:
    """Async: kasih role reward ke member yang levelnya memenuhi syarat.

    Sumber: config global (nama role) + dashboard per-server (role_id, JSON).
    """
    from src import config
    rewards = config.settings.level_roles_list()
    for threshold, nama in rewards:
        if threshold > level:
            break
        role = discord.utils.get(member.guild.roles, name=nama)
        if role is None or role in member.roles:
            continue
        try:
            await member.add_roles(role, reason=f"Reward level {threshold}")
            log.info("%s dapat role reward '%s' (level %d).", member, nama, level)
        except discord.Forbidden:
            log.warning("Gagal kasih role reward '%s' — role bot harus di atasnya.", nama)
            break
    # Tambahan dari dashboard: [{"level": 5, "role_id": "123..."}]
    try:
        from src.cogs.dashboard_sync import get_guild_setting
        import json

        mentah = get_guild_setting(member.guild.id, "leveling_roles", "")
        if mentah:
            for item in json.loads(mentah):
                try:
                    threshold = int(item.get("level", 0))
                    role_id = int(item.get("role_id", 0))
                except (ValueError, TypeError, AttributeError):
                    continue
                if threshold > level or not role_id:
                    continue
                role = member.guild.get_role(role_id)
                if role is None or role in member.roles:
                    continue
                try:
                    await member.add_roles(role, reason=f"Reward level {threshold} (dashboard)")
                    log.info("%s dapat role reward dashboard '%s' (level %d).", member, role.name, level)
                except discord.Forbidden:
                    log.warning("Gagal kasih role reward dashboard '%s'.", role_id)
                    break
    except Exception:
        log.warning("Gagal baca leveling_roles dashboard", exc_info=True)


def tambah_xp(conn, guild_id: int, user_id: int, jumlah: int) -> tuple[int, bool]:
    """Tambah XP ke user, handle level-up loop. Return (level_baru, naik_level)."""
    if jumlah <= 0:
        row = conn.execute(
            "SELECT level FROM users WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        ).fetchone()
        if row:
            return row[0], False
        return 1, False

    # BEGIN IMMEDIATE cegah lost update saat dua coroutine pakai koneksi beda.
    # Jika sudah dalam transaksi (caller pakai `with conn:`), sqlite error -> abaikan.
    try:
        conn.execute("BEGIN IMMEDIATE")
    except sqlite3.OperationalError:
        # "cannot start a transaction within a transaction" — aman, lanjut
        pass

    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT xp, level FROM users WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
        row = cur.fetchone()
        if row is None:
            current_xp = 0
            current_level = 1
            is_new = True
        else:
            current_xp, current_level = row
            is_new = False

        level_awal = current_level
        current_xp += jumlah

        while current_xp >= (current_level * 150):
            current_xp -= (current_level * 150)
            current_level += 1

        if is_new:
            cur.execute(
                "INSERT INTO users (user_id, guild_id, xp, level) VALUES (?, ?, ?, ?)",
                (user_id, guild_id, current_xp, current_level),
            )
        else:
            cur.execute(
                "UPDATE users SET xp = ?, level = ? WHERE user_id = ? AND guild_id = ?",
                (current_xp, current_level, user_id, guild_id),
            )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise

    naik = current_level > level_awal
    return current_level, naik


def hitung_menit(durasi_detik: float) -> int:
    """Durasi detik -> menit bulat ke bawah. <60 detik = 0."""
    if durasi_detik < 60:
        return 0
    return int(durasi_detik // 60)
