# Otomatisasi M1: Senin & Kamis 07.00 WIB, maks 4 kredit, notifikasi Telegram
## Setup untuk n8n di Docker Desktop

```
Windows Task Scheduler (Senin & Kamis 07.00)
  └─ tools\jalankan_otomatis.bat
       └─ Python: run_otomatis.py  (Kalodata API → filter → skor → berburu footage seller)
            ├─ simpan lokal: data\hasil_terakhir.pkl, data\footage_scout.json  → Streamlit
            └─ POST JSON → http://localhost:5678/webhook/m1-otomatis  (n8n di Docker)
                              └─ n8n: cek token → Data Table m1_kandidat + pesan Telegram
```

**Kenapa begini?** n8n di Docker berjalan di dalam container Linux, jadi tidak bisa menjalankan Python/venv di Windows.
Windows yang menjalankan skrip, sedangkan n8n hanya menerima hasil, menyimpannya, dan mengirim notifikasi.

| Otomatis | Tetap manual (Streamlit) |
|---|---|
| Cek saldo kredit, batal bila < 1 kredit | Konfirmasi akun seller resmi (tombol ✅ di Langkah 3) |
| Tarik data API → 6 filter → skor → snapshot tren | Isi timestamp 4 adegan |
| Info toko (sekali per toko). Toko dengan omzet akun sendiri Rp0 dilewati | Minta izin video ke seller |
| Daftar video → saran akun seller → Top 5 yang punya footage seller | Gerbang Langkah 4 → antrean VEO3 |
| Kandidat ke Data Table + ringkasan ke Telegram | |

Anggaran 4 kredit = 40 panggilan API (ranking ±6, cadangan footage 10, detail produk ±24).
Kalau Telegram sering melaporkan "lolos < 20", ubah `--maks-kredit 4` menjadi `5` di `tools\jalankan_otomatis.bat`.

---

## Langkah 1 — Uji skrip di laptop (wajib, sekali)

Di PowerShell, di folder proyek (misalnya `C:\affiliate\m1_riset`):
```
.venv\Scripts\python.exe run_otomatis.py --maks-kredit 4
```
Hasil yang diharapkan: satu baris JSON berisi `"status": "ok"`, dan log tersimpan di `data\log_otomatis.txt`.
Pastikan `.env` sudah berisi `KALODATA_API_KEY` dan `N8N_TOKEN`.
⚠️ Uji ini memakai kredit asli (≤4). Hasil di hari yang sama diambil dari cache, jadi menjalankan ulang tidak memakai kredit lagi.

## Langkah 2 — Pastikan Docker & n8n hidup otomatis

1. Docker Desktop → **Settings → General → "Start Docker Desktop when you sign in"** ✅
2. Container n8n harus punya **restart policy `unless-stopped`** (atau `always`).
   - Kalau memakai docker compose: tambahkan `restart: unless-stopped` di service n8n, lalu jalankan `docker compose up -d`.
   - Kalau memakai `docker run`: `docker update --restart unless-stopped <nama_container_n8n>`
3. Port 5678 harus dipetakan ke Windows (`-p 5678:5678`). Uji dengan membuka http://localhost:5678 di browser.

Skrip mencoba webhook sampai 5 kali dengan jeda 60 detik, jadi aman walau Docker baru menyala.

## Langkah 3 — Bot Telegram (sekali)

1. Di Telegram, chat **@BotFather** → `/newbot` → beri nama → salin **token**.
2. Kirim pesan apa saja ke bot baru Anda.
3. Buka `https://api.telegram.org/bot<TOKEN>/getUpdates` di browser, lalu salin angka di `"chat":{"id": ...}`.
4. Di n8n: **Credentials → New → Telegram API** → tempel token.

## Langkah 4 — Data Table `m1_kandidat`

n8n → **Data tables → Create** `m1_kandidat`:
- String: `kunci, tanggal, produk_id, nama, toko, kategori, flag_tren, status, alasan, saran_handle_seller, video_seller_1`
- Number: `peringkat, harga, omzet_7h, pertumbuhan_pct, jumlah_creator, komisi_pct, skor_akhir, omzet_akun_toko, jumlah_video_seller`
- Boolean: `handle_terverifikasi`

## Langkah 5 — Workflow n8n `M1 Otomatis`

Susunan node:
```
Webhook ─► IF (token benar?) ─► Code "Parse" ─┬─► Code "Pecah kandidat" ─► Data Table (Upsert)
                                              └─► Telegram (Send Message)
```
1. **Webhook**: HTTP Method `POST`, Path `m1-otomatis`, Respond `Immediately`.
2. **IF**: `{{ $json.headers["x-m1-token"] }}` **is equal to** token yang sama dengan `N8N_TOKEN` di `.env`.
   Cabang *false* tidak dihubungkan ke mana-mana (permintaan liar diabaikan).
3. **Code "Parse"** (Run Once for All Items) → tempel isi `n8n/kode_parse.js`.
4. **Code "Pecah kandidat"** → tempel isi `n8n/kode_pecah_kandidat.js` →
   **Data Table**: Resource Row, Operation **Upsert**, tabel `m1_kandidat`, kolom pencocok `kunci`, kolom dipetakan otomatis.
5. **Telegram**: Send Message, Chat ID Anda, Text `{{ $json.telegram_teks }}` (sambungkan dari "Parse").
6. Klik **Save** lalu **Activate** (tombol aktif di kanan atas).

Uji dari PowerShell (memakai kredit ≤4, atau 0 kalau hari ini sudah pernah jalan):
```
tools\jalankan_otomatis.bat
```
Hasil yang diharapkan: pesan Telegram masuk dan baris baru muncul di `m1_kandidat`.

## Langkah 6 — Jadwal Windows Task Scheduler

PowerShell **sebagai Administrator** (sesuaikan path):
```
schtasks /Create /TN "M1 Riset Otomatis" /SC WEEKLY /D MON,THU /ST 07:00 /TR "C:\affiliate\m1_riset\tools\jalankan_otomatis.bat"
```
Lalu buka **Task Scheduler → Task Scheduler Library → M1 Riset Otomatis → Properties**:
- Tab **Settings**: centang **"Run task as soon as possible after a scheduled start is missed"** (agar task tetap berjalan bila laptop mati pukul 07.00).
- Tab **Conditions**: hilangkan centang **"Start the task only if the computer is on AC power"** jika laptop sering memakai baterai.
- Opsional: tab **Conditions** → **"Wake the computer to run this task"**.

Uji: klik kanan task → **Run**, lalu lihat Telegram.

## Kalau ada masalah

| Gejala | Cek |
|---|---|
| Tidak ada pesan Telegram | `data\log_otomatis.txt`: baris `webhook gagal` berarti n8n/Docker mati atau workflow belum di-Activate |
| Telegram: `GAGAL ... Saldo kredit` | Isi ulang kredit di kalodata.com/open-center |
| Telegram: `lolos < 20` | Naikkan `--maks-kredit` di file .bat |
| Webhook 404 | URL harus `/webhook/` (bukan `/webhook-test/`) dan workflow harus aktif |

## Contoh pesan Telegram
```
M1 Riset 2026-11-12 - OK
Lolos filter: 24 (target 20) dari 610 produk
Kredit: 3.9 terpakai, sisa 4.3

SIAP ISI TIMESTAMP (2):
#1 SMAEL Jam Tangan Analog Digital Sport ...
  skor 72.0 | komisi 20.0% | 18 creator
  seller? @smaelwatch.id (CEK MANUAL)
  https://www.tiktok.com/@smaelwatch.id/video/...

TUGAS ANDA: buka Streamlit > Langkah 3: konfirmasi handle seller, isi timestamp 4 adegan, lalu Langkah 4 Gerbang.
```
