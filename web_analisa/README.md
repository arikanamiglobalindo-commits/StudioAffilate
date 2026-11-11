# Analisa Produk TikTok Shop (Kalodata Open API)

Dashboard riset produk: pencarian + filter, tabel peringkat dengan skor potensi, grafik tren 7/30/90 hari, perbandingan hingga 3 produk, dan ekspor CSV.

## Menjalankan

```bash
cp .env.example .env.local   # isi KALODATA_API_KEY
npm install
npm run dev                  # http://localhost:3000
```

Di balik proxy perusahaan, jalankan dengan `NODE_USE_ENV_PROXY=1` agar server memakai `HTTPS_PROXY`.

## Arsitektur

- `lib/kalodata.ts` — satu-satunya tempat yang memanggil Kalodata (`POST https://www.kalodata.com/openapi/v1/...`, header `secret-key`). Hanya berjalan di server; key tidak pernah sampai ke browser.
- Cache in-memory 15 menit + dedup request kembar + retry untuk error jaringan, supaya kredit API tidak terbuang.
- `app/api/*` — proxy tipis yang memvalidasi semua input sebelum diteruskan.
- `lib/normalize.ts` — konversi angka/persen dan rumus skor potensi.
- `lib/mock.ts` — data demo sintetis; hanya dipakai bila pengguna menekan "data demo" atau `KALODATA_MOCK=1`.

## Endpoint Kalodata yang dipakai

| Fitur | Endpoint | Catatan |
|---|---|---|
| Tabel peringkat | `/tiktok/product/rank` | periode: lastDay, last7Day, last30Day; maks. 5 halaman |
| Tren produk | `/tiktok/product/detail` | `revenue_trend` = revenue harian tanpa tanggal; diberi label H-n |
| Cari kategori | `/tiktok/category/searchByKeyword` | |
| Sisa kredit | `GET /credit/balance` | |

## Skor potensi

Skor 0–100 = rata-rata tertimbang persentil produk di antara hasil yang sedang tampil: revenue 35%, pertumbuhan revenue 30%, unit terjual 20%, komisi 15%. Ini peringkat relatif buatan aplikasi, bukan metrik Kalodata dan bukan prediksi.
