"""
n8n_client.py — Mengirim produk berstatus KIRIM ke antrean n8n Data Table.

KEPUTUSAN TEKNIS:
- Lewat WEBHOOK n8n (Webhook -> Data Table: Upsert -> Respond), bukan menulis
  ke database n8n langsung. Alasan: webhook adalah antarmuka resmi n8n, tidak
  rusak saat n8n di-update, dan workflow bisa memvalidasi data dulu.
- Setiap baris punya 'kunci' = produk_id + tanggal data. Di n8n dipakai untuk
  Upsert, dan di sisi Python dicatat di tabel 'terkirim' -> tidak ada kiriman ganda.
- Kolom dibuat datar (teks/angka) karena Data Table n8n tidak menyimpan objek
  bersarang; daftar klip dikirim juga sebagai teks JSON di 'klip_json'.
"""
import json
import time

import requests

from . import db


def buat_payload(baris_gerbang: dict, produk: dict, tanggal_data: str) -> dict:
    klip = {c["adegan"]: c for c in baris_gerbang["klip"]}

    def k(adg, field, default=""):
        return klip.get(adg, {}).get(field, default)

    p = {
        "kunci": f"{produk['produk_id']}_{tanggal_data}",
        "produk_id": str(produk["produk_id"]),
        "nama": produk["nama"], "toko": produk["toko"],
        "kategori": produk["kategori_m1"],
        "url_produk": produk.get("url_produk", ""),
        "harga": float(produk["harga"]), "omzet_7h": float(produk["omzet_7h"]),
        "pertumbuhan_pct": round(float(produk["pertumbuhan_pct"]), 1),
        "jumlah_creator": int(produk["jumlah_creator"]),
        "komisi_pct": round(float(produk["komisi_pct"]), 2),
        "skor_akhir": float(produk["skor_akhir"]),
        "skor_komisi": float(produk["skor_komisi"]),
        "skor_pertumbuhan": float(produk["skor_pertumbuhan"]),
        "skor_kepadatan": float(produk["skor_kepadatan"]),
        "flag_tren": ",".join(produk.get("flag_tren") or []),
        "adegan_seller": baris_gerbang["adegan_seller"],
        "ada_footage_berisiko": any(c["berisiko"] for c in baris_gerbang["klip"]),
        "tanggal_data": tanggal_data,
        "status": "antre",            # dipakai pipeline VEO3: antre -> diproses -> selesai
        "klip_json": json.dumps(baris_gerbang["klip"], ensure_ascii=False),
    }
    for adg in ("masalah", "demo", "hasil", "detail"):
        p[f"{adg}_url"] = k(adg, "url")
        p[f"{adg}_mulai"] = k(adg, "mulai_detik", 0.0)
        p[f"{adg}_selesai"] = k(adg, "selesai_detik", 0.0)
        p[f"{adg}_hak"] = k(adg, "status_hak")
    return p


def tes_koneksi(url: str, token: str = "", timeout: float = 8.0) -> tuple[bool, str]:
    """Kirim ping {'tipe':'ping'}. Workflow n8n sebaiknya membalas 200 tanpa menulis tabel."""
    try:
        r = requests.post(url, json={"tipe": "ping"}, headers={"X-M1-Token": token}, timeout=timeout)
        return r.ok, f"HTTP {r.status_code}: {r.text[:200]}"
    except requests.RequestException as e:
        return False, f"Tidak bisa terhubung: {e.__class__.__name__} — n8n sudah jalan? workflow aktif?"


def kirim(payloads: list[dict], url: str, token: str = "", ulang: int = 3,
          paksa: bool = False, db_path=None) -> list[dict]:
    """Kirim satu per satu (lebih mudah dilacak). Retry dengan jeda 1s, 2s, 4s."""
    hasil = []
    for p in payloads:
        if not paksa and db.sudah_terkirim(p["kunci"], db_path):
            hasil.append({"kunci": p["kunci"], "ok": True, "pesan": "dilewati (sudah pernah terkirim)"})
            continue
        pesan, ok = "", False
        for i in range(ulang):
            try:
                r = requests.post(url, json={"tipe": "produk", **p},
                                  headers={"X-M1-Token": token}, timeout=15)
                ok, pesan = r.ok, f"HTTP {r.status_code}: {r.text[:200]}"
                if ok or 400 <= r.status_code < 500:
                    break  # 4xx = salah konfigurasi, tidak perlu diulang
            except requests.RequestException as e:
                pesan = f"{e.__class__.__name__}"
            time.sleep(2 ** i)
        if ok:
            db.catat_terkirim(p["kunci"], p["produk_id"], p["tanggal_data"], pesan, db_path)
        hasil.append({"kunci": p["kunci"], "ok": ok, "pesan": pesan})
    return hasil
