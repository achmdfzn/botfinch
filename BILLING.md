# BILLING.md — Finch Premium Commerce (Payment Gateway)

Dokumen ini mencatat desain billing VIP Finch (checkout Midtrans Snap /
Xendit Invoice), fakta yang **terverifikasi dari dokumentasi resmi** saat
implementasi (23 Oktober 2026), dan batas kejujurannya: apa yang tidak
terjangkau / tidak diuji live.

> ⚠️ **Sandbox LIVE TIDAK DAPAT DIUJI di lingkungan pengembangan ini** —
> tidak ada credential merchant (server key / secret key / callback token)
> yang tersedia, jadi tidak ada satu pun panggilan nyata ke Midtrans/Xendit
> yang dilakukan. Semua verifikasi perilaku memakai **mock & fixture**
> (signature SHA512 dihitung lokal dari server key tes, fetch di-mock).
> Uji sandbox end-to-end adalah langkah manual pertama setelah deploy
> dengan credential sandbox asli (lihat "Urutan deployment").

---

## 1. Riset: terverifikasi vs tidak terjangkau

### Terverifikasi dari docs resmi Midtrans (docs.midtrans.com)

| Fakta | Sumber resmi yang dibaca |
| --- | --- |
| Snap create transaction: `POST https://app.sandbox.midtrans.com/snap/v1/transactions` (production: `https://app.midtrans.com/snap/v1/transactions`) | Integration Guide — Snap |
| Auth: `Authorization: Basic base64(serverKey + ":")` (username = Server Key, password kosong) | Integration Guide — Snap |
| Respons create: `{ token, redirect_url }` | Integration Guide — Snap |
| `transaction_details.order_id` unik, `gross_amount` integer rupiah | Integration Guide — Snap |
| Signature notifikasi: `signature_key = SHA512(order_id + status_code + gross_amount + ServerKey)`, gross_amount dipakai **mentah** dari payload (format `"10000.00"`) | Handle Notifications; HTTP(S) Notification / Webhooks |
| Notifikasi harus idempoten (Midtrans bisa mengirim event yang sama 2x) dan bisa datang tidak berurutan | Handle Notifications |
| GET status: `GET https://api.sandbox.midtrans.com/v2/{order_id}/status` (production: `api.midtrans.com`) | GET Status API Requests; Transaction Status |
| Status transaksi: `capture`, `settlement`, `pending`, `deny`, `cancel`, `expire`, `refund`; dari `settlement` bisa lanjut ke `refund`, `chargeback`, `partial_refund`, `partial_chargeback` | Transaction Status; Transaction Status Cycle |
| Sukses dibaca dari gabungan: status_code `200` + fraud_status `accept` + transaction_status `settlement`/`capture` | Handle Notifications |
| `callbacks.finish` = URL redirect setelah pembayaran (di Snap juga bisa disetel di dashboard) | JSON Objects; Create Checkout Token API |
| Kedaluwarsa Snap per transaksi memakai objek `expiry: { unit: "minutes", duration: 60 }` (unit: day/hour/minute) | JSON Objects; Expire a Snap Session |
| Notifikasi dikirim POST JSON ke *Payment Notification URL* yang disetel di dashboard Midtrans (Settings > Configuration) dan URL harus bisa dijangkau publik via HTTPS | HTTP(S) Notification / Webhooks |

Catatan koreksi riset: field `expiry_duration` yang dikenal dari Core API
adalah bagian `custom_expiry` (API charge langsung), **bukan** field Snap.
Untuk Snap, implementasi memakai objek `expiry { unit, duration }` di atas.

### Terverifikasi dari docs resmi Xendit (docs.xendit.co & kanal resmi Xendit)

| Fakta | Sumber resmi yang dibaca |
| --- | --- |
| Create invoice (legacy v2): `POST https://api.xendit.co/v2/invoices`; contoh payload resmi memuat `external_id`, `amount`, `description`, `invoice_duration` (detik), `customer`, `success_redirect_url`, `failure_redirect_url`, `currency: "IDR"` | Halaman migrasi resmi docs.xendit.co ("Migrate from (legacy) Payment Links/Invoice to Payment Session") yang menampilkan contoh payload Invoice legacy utuh |
| Method create/get: `POST /v2/invoices`, `GET /v2/invoices/{invoice_id}` | Dokumentasi SDK resmi Xendit (xendit-node / xendit-python / xendit-php di GitHub organisasi Xendit) |
| Objek invoice/callback memuat `id`, `external_id`, `status`, `amount`, `paid_amount`, `paid_at`, `currency` | SDK resmi Xendit (InvoiceApi / objek callback invoice) |
| Status invoice: `PENDING`, `PAID`, `SETTLED`, `EXPIRED` | SDK resmi Xendit; halaman status Payment Link docs.xendit.co (Paid = sudah dibayar; Settled = dana sudah settle ke akun dan bisa ditarik — tidak semua invoice mencapai Settled) |
| Webhook diverifikasi lewat header `x-callback-token` yang dibandingkan dengan *Webhook Verification Token* di dashboard (Settings > Developers > Webhooks) | Artikel resmi help.xendit.co tentang integrasi API end-to-end |
| Node library resmi memakai `Authorization: Basic base64(secretKey + ":")` untuk POST `/v2/invoices` | Blog/library resmi Xendit (contoh kode Node.js) |

Catatan: halaman API reference Xendit saat ini menonjolkan produk baru
(Payment Session); Invoice v2 diperlakukan Xendit sebagai **legacy** yang
sedang dimigrasikan. Endpoint v2 di atas tetap yang dipakai implementasi
ini sesuai kontrak proyek, tetapi status dukungan jangka panjangnya perlu
dicek ulang ke Xendit sebelum produksi.

### TIDAK diverifikasi (sengaja tidak dikarang)

- **Biaya / MDR / fee per transaksi** kedua provider: tidak dibaca dari
  halaman resmi mana pun saat riset ini dan tidak dicantumkan di sini.
  Cek halaman pricing / dashboard merchant masing-masing.
- **Status/verifikasi akun merchant** Finch (apakah sudah lolos KYC/KYB,
  dokumen legal apa yang diminta secara persis): bukan fakta dokumentasi
  publik yang terbaca — tergantung akun nyata owner.
- Pemisahan test/live Xendit: halaman yang terbaca tidak menegaskan base
  URL terpisah; implementasi memakai satu base `https://api.xendit.co`
  sesuai contoh resmi. Mode test/live mengikuti jenis API key yang
  diterbitkan dashboard (asumsi standar Xendit — verifikasi saat setup).
- SLA, batas refund per metode pembayaran, dan jadwal settlement dana:
  tidak diverifikasi; lihat dashboard/kontrak merchant.

---

## 2. Perbandingan Midtrans vs Xendit (hanya fakta terverifikasi di atas)

| Aspek | Midtrans Snap | Xendit Invoice (v2) |
| --- | --- | --- |
| Pola checkout | Buat transaksi di Snap API → `redirect_url` hosted Snap | Buat invoice → `invoice_url` hosted Xendit |
| Create | `POST {snap}/snap/v1/transactions` | `POST https://api.xendit.co/v2/invoices` |
| Auth API | Basic `base64(serverKey + ":")` | Basic `base64(secretKey + ":")` |
| Base URL sandbox vs production | Beda host: `app.sandbox.`/`api.sandbox.` vs `app.`/`api.` (dipilih `MIDTRANS_IS_PRODUCTION`) | Satu base `api.xendit.co` (lihat catatan test/live di §1) |
| Verifikasi webhook | `signature_key` di body = SHA512(order_id+status_code+gross_amount+ServerKey), dibandingkan timing-safe | Header `x-callback-token` == Webhook Verification Token dashboard, dibandingkan timing-safe |
| ID order merchant | `order_id` | `external_id` |
| Status lunas | `settlement`; `capture` + fraud `accept` | `PAID` atau `SETTLED` |
| Status kedaluwarsa | `expire` | `EXPIRED` |
| Nominal di payload status | `gross_amount` string `"50000.00"` (wajib pola 2 desimal, sen `00`) | `paid_amount` ?? `amount` (number) |
| Ambil status aktif | `GET /v2/{order_id}/status` | `GET /v2/invoices/{invoice_id}` |
| Kedaluwarsa per transaksi | `expiry { unit: "minutes", duration: 60 }` | `invoice_duration: 3600` (detik) |

Keduanya sama-sama: hosted checkout (tidak ada data kartu yang menyentuh
server Finch), webhook sebagai sumber kebenaran status (redirect pulang
hanya untuk UX), dan pola Basic auth server-key.

---

## 3. Arsitektur

```
UI (worker lain) ──POST /api/guilds/[id]/billing/checkout──▶ route checkout
                                                              │ harga dari env, BUKAN body
                                                              ▼
lib/billing.ts ── plan vip_monthly, parser harga, provider aktif, state machine
lib/payments/
  types.ts    ── kontrak PaymentProvider (createCheckout/fetchStatus/verifyWebhook)
  midtrans.ts ── Snap + signature SHA512 + GET status
  xendit.ts   ── Invoice v2 + x-callback-token + GET invoice
  index.ts    ── getProviderById / getActiveProvider (null bila credential tak lengkap)
  service.ts  ── processProviderStatus = JALUR TUNGGAL pemrosesan status
                 + handleProviderWebhook (dipakai kedua route webhook)
lib/db.ts ── billing_orders, webhook events, entitlement
```

Prinsip:

1. **Harga hanya dari server**: harga default katalog Rp65.000,
   dioverride oleh env `BILLING_VIP_PRICE_IDR` bila diisi digit murni
   > 0. Env kosong = harga default; env terisi tapi invalid
   (non-digit, 0, negatif, desimal) = billing nonaktif fail-closed
   (bukan diam-diam kembali ke default). Field harga/tier apa pun dari
   body checkout diabaikan.
2. **Satu jalur pemrosesan status** (`processProviderStatus`): webhook dan
   rekonsiliasi malas (GET detail order memicu `fetchStatus` bila data
   basi > 30 detik) memanggil fungsi yang sama — tidak ada logika ganda.
3. **Idempotensi via klaim atomik**: entitlement hanya diterapkan pemenang
   `claimBillingOrderPaid` di DB. Webhook duplikat / retry provider /
   balapan webhook-vs-rekonsiliasi kalah klaim → `already_applied`,
   durasi VIP **tidak** bertambah ganda. Klaim hanya menyetel penanda
   klaim (`paid_at`); penanda penerapan (`entitlement_applied_at`)
   di-set setelah penerapan berhasil — klaim yang terputus di tengah
   (proses mati) dipulihkan otomatis pada event/rekonsiliasi
   berikutnya (klaim berumur > 60 detik, dijaga atribusi
   `provider_entitlement_id`), bukan hilang permanen.
   Perpanjangan entitlement dihitung di dalam SQL dari baris yang
   sedang ditulis (bukan read-modify-write di TypeScript), jadi dua
   order berbeda untuk guild yang sama tidak bisa saling menimpa masa
   berlaku.
4. **Notifikasi Midtrans tidak dipercaya untuk status**: signature
   SHA512 Midtrans tidak mencakup `transaction_status`/`fraud_status`,
   jadi handler webhook Midtrans memakai notifikasi hanya sebagai
   pemicu lalu mengambil status resmi lewat API provider
   (`fetchStatus`) sebelum memproses; bila API tak terjangkau, webhook
   dijawab 502 agar provider me-retry. (Token callback Xendit
   mengautentikasi seluruh body, jadi jalur Xendit memproses body
   langsung.)
5. **Nominal diverifikasi sebelum klaim**: `amountIdr` provider harus sama
   persis dengan `amount_idr` order dan currency harus IDR; selain itu
   `amount_mismatch` tanpa perubahan apa pun.
6. **Fail-closed**: signature/token webhook salah → 401 sebelum data
   disentuh; billing tak terkonfigurasi → 503; detail order guild lain →
   404 (anti-IDOR).
7. Order aktif (created/pending, belum kedaluwarsa) dipakai ulang saat
   checkout agar dobel-klik tidak membuat dua tagihan; order aktif yang
   menggantung tanpa tautan bayar ditutup dan diganti order baru, dan
   indeks unik parsial di DB menjamin satu order aktif per (guild,
   plan) walau dua checkout berjalan bersamaan.

> **Catatan migrasi:** plan `vip_30d` diganti nama menjadi
> `vip_monthly` (durasi tetap 30 hari; 1 bulan = 30 hari) dan env
> `BILLING_VIP_30D_PRICE_IDR` diganti nama menjadi
> `BILLING_VIP_PRICE_IDR`. Order lama ber-`plan_id vip_30d` tetap
> terbaca di dashboard; checkout baru hanya memakai `vip_monthly`.
> **Jendela cutover:** pencarian order aktif dan indeks unik order
> aktif sama-sama per plan, jadi order `vip_30d` yang masih aktif
> (`created`/`pending`, berlaku ±60 menit sejak dibuat) tidak terlihat
> oleh checkout baru — guild yang sama sesaat bisa memegang satu order
> aktif dari tiap plan. Tangani saat deployment (lihat §6): deploy
> ketika tidak ada order `vip_30d` aktif, atau tutup paksa HANYA baris
> aktif plan lama. Order `paid`/terminal jangan pernah diubah
> `plan_id`-nya: riwayat dan snapshot order adalah jejak audit, dan
> settlement/refund order lama tetap bekerja dari snapshot
> `amount_idr`/`duration_days`-nya sendiri.

### Kontrak service (`processProviderStatus(order, status, { source })`)

| `status.kind` | Perilaku | Outcome |
| --- | --- | --- |
| paid (nominal & currency cocok) | klaim atomik → `applyPaymentToEntitlement` → tandai diterapkan | `applied:activated|extended|noop_permanent|blocked_suspended` |
| paid, klaim kalah | — | `already_applied` |
| paid, klaim yatim lama (proses mati sebelum penerapan) | penerapan dipulihkan / hanya ditandai bila atribusi cocok | `recovered:<hasil>` / `recovered_marked` |
| paid, nominal/currency beda/tak terbukti | tanpa perubahan | `amount_mismatch` (webhook: HTTP 400) |
| paid, order sudah failed/cancelled/refunded/disputed | tanpa perubahan | `settlement_after_terminal` (webhook: HTTP 200, tercatat) |
| pending | transisi dari `created` saja | `pending` / `ignored` |
| failed / cancelled / expired | transisi dari `created`/`pending` | `transitioned` / `ignored` |
| refunded | nominal cocok (bila dilaporkan) → transisi dari `paid` → kurangi masa sebesar durasi order | `refunded` / `ignored` / `amount_mismatch` |
| disputed | transisi dari `paid`, entitlement **tidak** diubah | `disputed` / `ignored` |
| unknown (termasuk partial refund) | — | `ignored` |

Outcome webhook lain → HTTP 200 `{ ok: true, outcome }`.

---

## 4. State machine order & kebijakan

```
created ──▶ pending ──▶ paid ──▶ refunded
  │           │          └─────▶ disputed
  │           ├──▶ failed
  │           ├──▶ cancelled
  │           └──▶ expired ──▶ paid   (late settlement)
  └───────────┴──▶ (failed/cancelled/expired dari created juga sah)
```

Sumber kebenaran transisi adalah `ORDER_TRANSITIONS` di `lib/billing.ts`
(helper `transitionSources(to)` menurunkan daftar status asal yang sah,
dan `canTransitionOrder` memvalidasi pasangan) — service memakainya untuk
`transitionBillingOrder`; jalur lunas dijaga klaim atomik
(`claimBillingOrderPaid`: satu statement CTE yang hanya menang bila
penanda klaim `paid_at` dan penanda penerapan `entitlement_applied_at`
masih kosong dan status bukan terminal
`failed`/`cancelled`/`refunded`/`disputed` — status `expired` termasuk
yang boleh menang, sebagai late settlement).

Kebijakan:

- **Late settlement**: settlement yang tiba saat order `expired` tetap
  dihormati (uang benar-benar masuk) — klaim menang dengan
  `previousStatus = 'expired'` dan entitlement diberi note
  `late_settlement` untuk audit.
- **Settlement setelah terminal**: order `failed`/`cancelled`/`refunded`/
  `disputed` tidak pernah diaktifkan otomatis
  (`settlement_after_terminal`). Dana pada kasus ini ditangani manual
  owner (refund/inspeksi di dashboard provider), bukan auto-VIP.
- **Capture challenge (Midtrans)**: kartu yang di-challenge FDS dipetakan
  ke `pending`, **bukan** paid — VIP tidak aktif sebelum fraud jelas
  accept/settlement.
- **Refund**: hanya refund **penuh** (`refund` Midtrans) yang mengurangi
  entitlement, dan hanya sebesar **durasi order yang direfund**
  (`revokeEntitlementForRefund` memundurkan `expires_at` sebesar durasi
  itu; status menjadi `revoked` hanya bila sisa masa habis). Refund
  dicatat dari order berstatus `paid` saja, dan nominal refund yang
  dilaporkan provider — bila ada — harus cocok dengan nominal order.
- **Partial refund**: `partial_refund` / `partial_chargeback` dipetakan ke
  `unknown` → `ignored`. Sebagian dana kembali bukan alasan mencabut VIP
  penuh secara otomatis; tangani manual bila perlu.
- **Dispute/chargeback**: order ditandai `disputed`, entitlement dibiarkan
  apa adanya menunggu review owner — dispute bisa dimenangkan merchant,
  jadi pencabutan otomatis akan merugikan pembeli yang sah.

---

## 5. Setup merchant & pendaftaran webhook

Ganti `<domain>` dengan domain publik dashboard produksi
(nilai `APP_BASE_URL`).

URL webhook yang **wajib didaftarkan**:

- Midtrans: `https://<domain>/api/payments/webhook/midtrans`
- Xendit: `https://<domain>/api/payments/webhook/xendit`

### Midtrans

1. Daftar/login Merchant Administration Portal (MAP); ambil **Server Key**
   & **Client Key** sandbox dari Settings > Access Keys.
2. Settings > Configuration: isi **Payment Notification URL** dengan URL
   webhook Midtrans di atas (harus HTTPS & terjangkau publik).
3. Isi env dashboard: `PAYMENT_PROVIDER=midtrans`,
   `MIDTRANS_SERVER_KEY=…`, `MIDTRANS_CLIENT_KEY=…`,
   `MIDTRANS_IS_PRODUCTION=false` (sandbox).
4. Untuk production: ganti key dengan key production &
   `MIDTRANS_IS_PRODUCTION=true`, daftarkan ulang Notification URL di
   mode production.

### Xendit

1. Daftar/login dashboard Xendit; buat **Secret API Key** di
   Settings > Developers > API Keys (beri izin tulis Invoice).
2. Settings > Developers > Webhooks: salin **Webhook Verification Token**
   ke env `XENDIT_CALLBACK_TOKEN`, dan setel callback URL *Invoices* ke
   URL webhook Xendit di atas (aktifkan notifikasi invoice dibayar &
   kedaluwarsa).
3. Isi env: `PAYMENT_PROVIDER=xendit`, `XENDIT_SECRET_KEY=…`,
   `XENDIT_CALLBACK_TOKEN=…`.

### Env bersama

- `BILLING_VIP_PRICE_IDR` — opsional: kosong = harga default katalog
  Rp65.000 untuk plan `vip_monthly` (1 bulan = 30 hari); isi
  `<integer rupiah digit murni, mis. 50000>` untuk mengoverride. Nilai
  invalid membuat checkout menjawab 503 `billing_not_configured`.
- `APP_BASE_URL=https://<domain>` — basis URL kembali setelah bayar
  (`/dashboard/<guildId>/billing/orders/<orderRef>`).

Semua secret server-side: **tanpa** prefix `NEXT_PUBLIC_`.

---

## 6. Urutan deployment

1. Jalankan `dashboard/schema.sql` di Postgres (membuat tabel billing &
   webhook events + entitlement) — sekali.
2. Setel env di atas di platform deploy (Vercel) untuk provider pilihan.
   **Migrasi env harga:** hapus `BILLING_VIP_30D_PRICE_IDR` (nama lama
   diabaikan total oleh kode baru) dan, bila ingin override, isi
   `BILLING_VIP_PRICE_IDR`. Perilaku berubah secara sadar: env harga
   kosong sekarang berarti harga default katalog **Rp65.000**, BUKAN
   billing nonaktif — deployment yang dulu "mematikan" billing dengan
   membiarkan env harga kosong akan mulai menjual seharga Rp65.000
   begitu `PAYMENT_PROVIDER` + credential terisi. Untuk menonaktifkan
   billing, kosongkan `PAYMENT_PROVIDER`. Pemakaian harga default
   dicatat sekali per proses sebagai `console.warn` di log server.
3. **Tutup jendela cutover rename plan:** pastikan tidak ada order
   `vip_30d` berstatus `created`/`pending` yang masih berlaku. Bila
   ada dan tidak bisa menunggu kedaluwarsa alaminya (±60 menit), tutup
   paksa HANYA baris aktif plan lama:
   `UPDATE billing_orders SET status = 'expired', updated_at = NOW() WHERE plan_id = 'vip_30d' AND status IN ('created', 'pending');`
   Jangan mengubah `plan_id` baris mana pun dan jangan menyentuh order
   `paid`/terminal.
4. Deploy dashboard.
5. Daftarkan URL webhook di dashboard provider (§5) — sesudah deploy,
   karena URL harus live saat provider memverifikasi/mengirim tes.
6. **Uji sandbox** (belum pernah diuji live dari lingkungan dev):
   checkout dari UI → bayar dengan instrumen tes sandbox provider →
   pastikan order menjadi `paid`, entitlement guild aktif 30 hari,
   webhook tercatat; uji juga skenario kedaluwarsa & nominal.
7. Baru kemudian ganti credential ke production + aktifkan mode
   production (`MIDTRANS_IS_PRODUCTION=true` untuk Midtrans).

Rollback / recovery:

- **Matikan billing seketika**: kosongkan `PAYMENT_PROVIDER` lalu
  redeploy — checkout menjawab 503, order & entitlement yang sudah
  ada tidak berubah. (Mengosongkan `BILLING_VIP_PRICE_IDR` TIDAK
  mematikan billing: env kosong berarti harga default katalog
  Rp65.000.)
- **Ganti provider**: ubah `PAYMENT_PROVIDER` + credential; order lama
  tetap diproses provider asalnya (rekonsiliasi & webhook memvalidasi
  `order.provider`), order baru memakai provider aktif.
- **Webhook hilang/terlambat**: tidak perlu tindakan darurat — membuka
  halaman detail order memicu rekonsiliasi `fetchStatus` untuk order
  created/pending yang basi > 30 detik lewat jalur service yang sama.
- **Settlement menggantung** (order terminal tapi dana masuk): cek
  outcome `settlement_after_terminal` di log webhook events; putuskan
  manual (aktifkan VIP via panel owner atau refund di dashboard
  provider). Jangan mengedit status order langsung di DB tanpa audit.

---

## 7. Checklist prasyarat produksi

- [ ] Akun merchant (provider pilihan) terdaftar & terverifikasi penuh
      oleh provider (status akun dikonfirmasi owner di dashboard
      provider — tidak diverifikasi dokumen ini).
- [ ] Credential **production** terpasang; credential sandbox tidak
      tertukar (Midtrans: `MIDTRANS_IS_PRODUCTION=true`).
- [ ] URL webhook production terdaftar & menerima event tes dari
      dashboard provider.
- [ ] Harga jual final terkonfirmasi: default katalog Rp65.000, atau
      `BILLING_VIP_PRICE_IDR` terisi nilai override yang disetujui owner.
- [ ] Uji sandbox end-to-end lulus (§6 langkah 6) sebelum go-live.
- [ ] Tidak ada order aktif `vip_30d` yang tertinggal dari versi lama
      (§6 langkah 3), atau jendela cutovernya sudah ditutup.
- [ ] Halaman legal siap: syarat & ketentuan pembelian, kebijakan refund,
      dan info kontak penjual dapat dijangkau pembeli.
- [ ] Kewajiban pajak & pencatatan penjualan ditangani owner (di luar
      cakupan kode ini).
- [ ] Monitoring: log outcome webhook (`amount_mismatch`,
      `settlement_after_terminal`) dipantau berkala — keduanya sinyal
      anomali yang butuh tindakan manual.

## 8. Pengujian yang dilakukan (mock/fixture)

Suite Vitest billing — `lib/payments.test.ts`,
`lib/billing-db.test.ts`, `lib/billing-checkout-route.test.ts`,
`lib/billing-orders-route.test.ts`, `lib/billing-webhook.test.ts` —
menutup: parser harga env, state machine (+ konsistensi
`transitionSources`), mapping status kedua provider, SQL klaim/apply/
refund (termasuk perpanjangan yang dihitung di SQL, refund proporsional,
kasus VIP kedaluwarsa), signature Midtrans valid/berubah/hilang,
konfirmasi otoritatif Midtrans (body settlement + API challenge →
pending; API tak terjangkau → 502), body null → 401, provider tak
terkonfigurasi → 503, token Xendit salah, idempotensi klaim (duplikat &
balapan), pemulihan klaim yatim, amount/currency mismatch, capture
challenge, expire, refund+kurangi-masa, checkout non-manager/503/
harga-dari-env/reused/order-gantung/unique-violation, GET orders
anti-IDOR + rekonsiliasi malas + throttle. Sekali lagi: **tidak ada**
uji live ke sandbox provider dari lingkungan ini (tanpa credential) —
lihat peringatan di atas.
