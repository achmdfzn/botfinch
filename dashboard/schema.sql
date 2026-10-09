-- Finch Dashboard schema (Vercel Postgres). Jalankan sekali via Vercel Storage > Query.
CREATE TABLE IF NOT EXISTS snapshots (
  id SERIAL PRIMARY KEY,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS guild_settings (
  guild_id TEXT PRIMARY KEY,
  settings JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Self-roles: emoji -> role pada pesan tertentu
CREATE TABLE IF NOT EXISTS selfroles (
  id SERIAL PRIMARY KEY,
  guild_id TEXT NOT NULL,
  message_id TEXT NOT NULL,
  emoji TEXT NOT NULL,
  role_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (guild_id, message_id, emoji)
);

-- Auto-responder: trigger teks -> balasan
CREATE TABLE IF NOT EXISTS autoresponses (
  id SERIAL PRIMARY KEY,
  guild_id TEXT NOT NULL,
  trigger TEXT NOT NULL,
  response TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (guild_id, trigger)
);

-- Permintaan giveaway dari dashboard, dieksekusi bot
CREATE TABLE IF NOT EXISTS giveaway_requests (
  id SERIAL PRIMARY KEY,
  guild_id TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  prize TEXT NOT NULL,
  winners INT NOT NULL DEFAULT 1,
  duration_minutes INT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  note TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_giveaway_requests_pending ON giveaway_requests (status) WHERE status = 'pending';

-- Permintaan embed dari dashboard, dieksekusi bot
CREATE TABLE IF NOT EXISTS embed_requests (
  id SERIAL PRIMARY KEY, guild_id TEXT NOT NULL, channel_id TEXT NOT NULL,
  title TEXT DEFAULT '', description TEXT DEFAULT '', color TEXT DEFAULT '2EC4B6',
  fields JSONB DEFAULT '[]', footer TEXT DEFAULT '',
  image_url TEXT DEFAULT '', thumbnail_url TEXT DEFAULT '',
  status TEXT DEFAULT 'pending', note TEXT DEFAULT '',
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_embed_requests_pending ON embed_requests(status) WHERE status = 'pending';

-- Pengumuman terjadwal / berulang dari dashboard, dieksekusi bot
CREATE TABLE IF NOT EXISTS announcements (
  id SERIAL PRIMARY KEY, guild_id TEXT NOT NULL, channel_id TEXT NOT NULL,
  message TEXT NOT NULL, run_at TIMESTAMPTZ, interval_minutes INT,
  enabled BOOLEAN DEFAULT TRUE, last_sent_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
