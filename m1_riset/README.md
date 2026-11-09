# M1 — Riset Produk TikTok Shop (Kalodata → Skor → Footage → Gerbang → n8n)

## 0. Validasi akses data Kalodata (keputusan sebelum menulis kode)

| Opsi | Stabil? | Sah? | Keputusan |
|---|---|---|---|
| **Kalodata Open API resmi** | Ya: JSON terstruktur, tanpa UI yang berubah-ubah | Ya: kunci dari kalodata.com/open-center/account | **UTAMA** |
| Export CSV/XLSX manual | Ya | Ya (fitur resmi) | **CADANGAN** bila API error atau kredit habis |
| Otomatisasi browser / scraper | Tidak | **Tidak**: ToS 4.1.8 melarang skrip otomatis | Ditolak |

Catatan API (cek dulu dengan tombol **Tes API** di Langkah 1):
- Bentuk request diambil dari klien open-source `sailtonight/kalodata-skill`, **bukan dokumentasi resmi**: POST JSON ke `https://www.kalodata.com/openapi/v1`, kunci di header `secret-key`.
- API memakai **kredit**. Harga dan syarat paket belum terverifikasi (ada sumber pihak ketiga yang menyebut Enterprise saja). Cek di Open Center sebelum dipakai rutin.
- Penghemat kredit yang sudah terpasang:
  - cache per hari (`data/api_cache/`)
  - batas panggilan per run
  - pra-saring lokal sebelum memanggil detail
  - ID kategori dicari sekali saja
- Pengecekan satuan otomatis: dari omzet ≈ harga × terjual, modul mendeteksi angka yang dikirim ×100 atau komisi/growth yang berbentuk pecahan.

## 1. Struktur & peta risiko

```
m1_riset/
├─ app.py                  UI Streamlit 4 langkah            → semua risiko
├─ m1/config.py            filter, kategori, bobot, adegan   → semua (dikunci)
├─ m1/parsing.py           "Rp1,2jt", "12,5%", "0:05"        → Akses Data
├─ m1/kalodata_api.py      klien Open API + cache + batas    → Akses Data
├─ m1/sumber_api.py        ranking→pra-saring→detail→toko    → Akses Data
├─ m1/importer.py          baca export CSV (cadangan)        → Akses Data
├─ m1/trend.py             snapshot mingguan, flag puncak    → Timing Tren
├─ m1/filters.py           6 filter + kategori + corong      → Timing Tren
├─ m1/scoring.py           skor komisi/pertumbuhan/kepadatan → Timing Tren
├─ m1/footage.py           oEmbed, status hak, 4 adegan      → Hak Footage
├─ m1/gate.py              Top 5 + alasan lolos/gagal        → ketiganya
├─ m1/n8n_client.py        kirim ke webhook n8n, anti ganda  → (integrasi)
├─ m1/db.py, pipeline.py   SQLite lokal, urutan proses
├─ tools/buat_data_contoh.py   data DUMMY untuk uji
├─ tests/test_m1.py        14 tes (parsing, filter, gerbang, n8n)
├─ tests/test_api.py       7 tes API vs server tiruan
└─ tests/mock_kalodata.py  server Kalodata TIRUAN (data acak) untuk uji tanpa kredit
```

| Fitur | Risiko yang ditangani | Cara menangani |
|---|---|---|
| Open API resmi + cache + batas panggilan | Akses Data | Sah sesuai ToS, kredit terkendali |
| Daftar video produk via API | Hak Footage | Handle pembuat video terlihat, sehingga seller dan affiliate langsung terpisah |
| Impor export manual (cadangan) | Akses Data | Tetap bisa riset walau API bermasalah |
| Pemetaan kolom + pratinjau | Akses Data | Header yang berubah tidak membuat angka salah baca |
| Parser Rupiah (jt/rb/M/K) | Akses Data | "M" dibaca miliar di format Indonesia dan juta di format Inggris |
| Snapshot mingguan | Timing Tren | Membandingkan minggu ini dengan minggu lalu |
| Flag `lewat_puncak`, `creator_melonjak` | Timing Tren | Penalti skor −15, dan gerbang langsung **TAHAN** |
| Skor kepadatan (omzet/creator) | Timing Tren | Produk yang sudah dikeroyok creator turun peringkatnya |
| oEmbed TikTok resmi | Hak Footage | Pemilik video dicek otomatis lalu dibandingkan dengan handle seller |
| Status hak 3 tingkat | Hak Footage | seller_izin 🟢 / seller 🟡 / affiliate_berisiko 🔴, sumber tercatat |
| Klip 1–15 detik | Hak Footage | Hasilnya suntingan baru, bukan re-upload utuh (kebijakan konten tidak orisinal) |
| Gerbang ≥3/4 adegan seller | Hak Footage | Produk tanpa footage aman tidak pernah dikirim |

## 2. Instalasi di Windows (sekali saja)

1. Install **Python 3.11+** dari python.org dan centang "Add python.exe to PATH".
2. Salin folder `m1_riset` ke misalnya `C:\affiliate\m1_riset`.
3. Buka **PowerShell** di folder itu (Shift + klik kanan → "Open PowerShell window here"):
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   copy .env.example .env
   ```
   Kalau `activate` ditolak, jalankan sekali: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
4. Edit `.env` dengan Notepad dan isi `KALODATA_API_KEY`, `N8N_WEBHOOK_URL`, serta `N8N_TOKEN` (lihat bagian 4).

## 3. Cara uji per file/fitur (Windows)

Semua perintah dijalankan di PowerShell setelah `.venv\Scripts\activate`.

| # | Uji | Perintah / langkah | Hasil yang diharapkan |
|---|---|---|---|
| 1 | Semua tes otomatis | `python -m pytest -q` | `25 passed` |
| 2 | Uji UI tanpa kredit | Jendela 1: `python tests\mock_kalodata.py 5680`. Jendela 2: `$env:KALODATA_BASE_URL="http://127.0.0.1:5680/openapi/v1"; $env:KALODATA_API_KEY="kunci-tes"; streamlit run app.py` | App terbuka dan memakai server tiruan |
| 3 | kalodata_api.py | Langkah 1 → **Tes API & cek saldo** | Saldo kredit tampil dan 1 baris produk mentah (JSON) |
| 4 | Kategori | **Cari ID kategori** → cek tabel → **Simpan** | Kategori Fashion dan Rumah Tangga tercentang |
| 5 | sumber_api.py | **Tarik data produk** | Catatan satuan, jumlah produk, dan jumlah panggilan (berbayar vs cache) |
| 6 | filters + scoring + trend | Langkah 2 → **Jalankan riset** | "≥ 20 produk lolos", corong, skor. Mock menghasilkan 46 |
| 7 | Video API + footage.py | Langkah 3 → **Ambil daftar video** → isi handle seller → pilih video → isi timestamp → simpan 4 klip | 🟡/🟢 untuk seller, 🔴 untuk affiliate lain |
| 8 | gate.py + n8n | Langkah 4 | Produk dengan ≥3 adegan seller berstatus **KIRIM**, lalu HTTP 200 dari n8n |
| 9 | Data asli | Hapus variabel `$env:` (tutup PowerShell), isi kunci asli di `.env`, jalankan `streamlit run app.py` | Tombol **Tes API** menampilkan saldo kredit asli |

**Setelah uji coba, hapus `data\m1.db`, `data\hasil_terakhir.pkl`, `data\kategori_api.json`, dan folder `data\api_cache`** agar snapshot dummy tidak tercampur dengan data asli.

## 4. Setup n8n (Webhook → Data Table)

1. Di n8n buka **Data tables** → **Create** dengan nama `m1_antrean`. Buat kolom (String kecuali disebut lain):
   `kunci, produk_id, nama, toko, kategori, url_produk, flag_tren, tanggal_data, status, klip_json,`
   `masalah_url, masalah_hak, demo_url, demo_hak, hasil_url, hasil_hak, detail_url, detail_hak` (String)
   `harga, omzet_7h, pertumbuhan_pct, jumlah_creator, komisi_pct, skor_akhir, skor_komisi, skor_pertumbuhan, skor_kepadatan, adegan_seller,`
   `masalah_mulai, masalah_selesai, demo_mulai, demo_selesai, hasil_mulai, hasil_selesai, detail_mulai, detail_selesai` (Number)
   `ada_footage_berisiko` (Boolean)
2. Buat workflow baru `M1 → Antrean`:
   - **Webhook**: Method `POST`, Path `m1-antrean`, Respond `Using 'Respond to Webhook' node`.
   - **IF**: `{{$json.body.tipe}}` equals `produk` **AND** `{{$json.headers["x-m1-token"]}}` equals token Anda.
     - *false* → **Respond to Webhook** (200, `{"ping":"ok"}`). Ping dan token salah tidak menulis tabel.
     - *true* → **Data Table** (Resource Row, Operation **Upsert**, tabel `m1_antrean`, kolom pencocok `kunci`). Petakan setiap kolom dari `{{$json.body.<nama_kolom>}}` → **Respond to Webhook** (200, `{"diterima":true}`).
3. **Activate** workflow, lalu salin **Production URL** (`.../webhook/m1-antrean`, bukan `/webhook-test/`) ke `.env`.
4. Workflow VEO3 (M2) membaca baris berstatus `antre` dan mengubahnya menjadi `diproses` → `selesai`.

## 5. Ritme mingguan (sesuai blueprint)

Senin: Langkah 1 (Tarik data via API) → Langkah 2 → kumpulkan footage untuk ±10 kandidat teratas (Langkah 3) → Langkah 4 → kirim.
Mulai minggu ke-2, flag tren aktif penuh karena snapshot minggu lalu sudah tersedia.

## 6. Otomatisasi (Senin & Kamis)

Lihat **`n8n/PANDUAN_OTOMATIS.md`**. Ringkasnya: n8n menjalankan `run_otomatis.py`, hasilnya masuk Data Table `m1_kandidat`, dan ringkasan dikirim ke Telegram. Konfirmasi handle seller, timestamp, dan Gerbang tetap Anda lakukan di Streamlit.

## 7. Batasan yang perlu diketahui

- Minimal 20 produk lolos **tidak bisa dijamin oleh kode**. Jumlahnya bergantung pada banyaknya baris yang Anda export. Kalau kurang, lihat kolom `gagal_di_filter_ini_saja` di corong lalu export lebih banyak halaman atau sub-kategori sebelum melonggarkan filter.
- Video dari akun seller **tetap milik seller**. Status 🟡 berarti Anda masih perlu meminta izin lewat chat toko dan menempel buktinya, supaya statusnya naik menjadi 🟢.
- Persona AI untuk hook/CTA: aktifkan label "AI-generated" di TikTok saat posting.
