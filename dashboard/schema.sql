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

-- Entitlement Free/VIP per guild: satu baris per guild.
-- Baris dibuat malas (lazy) saat guild pertama kali terlihat (ingest/sync)
-- dengan tier 'free'; pemberian VIP hanya lewat owner (admin/internal API).
CREATE TABLE IF NOT EXISTS guild_entitlements (
  guild_id TEXT PRIMARY KEY,
  tier TEXT NOT NULL DEFAULT 'free',
  status TEXT NOT NULL DEFAULT 'active',
  source TEXT NOT NULL DEFAULT 'default',
  starts_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ,
  provider_entitlement_id TEXT UNIQUE,
  provider_subscription_id TEXT,
  granted_by TEXT,
  note TEXT,
  bot_present BOOLEAN NOT NULL DEFAULT TRUE,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Log audit tiap perubahan entitlement (grant/extend/revoke)
CREATE TABLE IF NOT EXISTS entitlement_audit_log (
  id BIGSERIAL PRIMARY KEY,
  guild_id TEXT NOT NULL,
  actor_id TEXT,
  action TEXT NOT NULL,
  tier_before TEXT,
  tier_after TEXT,
  status_before TEXT,
  status_after TEXT,
  expires_before TIMESTAMPTZ,
  expires_after TIMESTAMPTZ,
  reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_entitlement_audit_log_guild ON entitlement_audit_log (guild_id, id DESC);

-- Billing otomatis (checkout provider eksternal -> webhook -> entitlement).
-- Order pembayaran per guild; sumber kebenaran status order ada di sini,
-- sedangkan hasil akhirnya (VIP aktif) tertulis di guild_entitlements.
CREATE TABLE IF NOT EXISTS billing_orders (
  id BIGSERIAL PRIMARY KEY,
  order_ref TEXT UNIQUE NOT NULL,
  buyer_user_id TEXT NOT NULL,
  guild_id TEXT NOT NULL,
  plan_id TEXT NOT NULL,
  amount_idr BIGINT NOT NULL,
  currency TEXT NOT NULL DEFAULT 'IDR',
  duration_days INT NOT NULL,
  status TEXT NOT NULL DEFAULT 'created',
  provider TEXT NOT NULL,
  provider_txn_id TEXT NULL,
  provider_redirect_url TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL,
  paid_at TIMESTAMPTZ NULL,
  entitlement_applied_at TIMESTAMPTZ NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_billing_orders_guild ON billing_orders (guild_id);
CREATE INDEX IF NOT EXISTS idx_billing_orders_buyer ON billing_orders (buyer_user_id);
CREATE INDEX IF NOT EXISTS idx_billing_orders_status ON billing_orders (status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_billing_orders_provider_txn
  ON billing_orders (provider_txn_id) WHERE provider_txn_id IS NOT NULL;
-- Satu order AKTIF per (guild, plan): menutup balapan dua POST checkout
-- bersamaan yang sama-sama lolos cek findActiveBillingOrder. Order yang
-- kedaluwarsa menurut waktu tetapi statusnya belum berubah ditutup
-- lebih dulu oleh route checkout sebelum insert baru.
CREATE UNIQUE INDEX IF NOT EXISTS idx_billing_orders_one_active
  ON billing_orders (guild_id, plan_id) WHERE status IN ('created', 'pending');

-- Log penerimaan webhook provider untuk dedupe: event_key unik, webhook
-- yang sama diterima ulang tidak diproses dua kali (INSERT ... DO NOTHING).
CREATE TABLE IF NOT EXISTS billing_webhook_events (
  id BIGSERIAL PRIMARY KEY,
  provider TEXT NOT NULL,
  event_key TEXT UNIQUE NOT NULL,
  order_ref TEXT NULL,
  provider_status TEXT NULL,
  received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
