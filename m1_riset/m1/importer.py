"""
importer.py — Membaca file EXPORT Kalodata (CSV/XLSX) tab Produk.

KEPUTUSAN TEKNIS (Risiko: AKSES DATA):
- Kalodata Terms of Service melarang "automated scripts to collect information"
  dan melewati pembatas akses. Jadi modul ini TIDAK login, TIDAK scraping,
  TIDAK otomatisasi browser. Anda klik "Export" di Kalodata secara manual,
  lalu file-nya diunggah ke Streamlit. Akun Kalodata aman dari blokir.
- Header export bisa berubah (bahasa UI / versi Kalodata). Karena itu kolom
  dicocokkan lewat alias (config.ALIAS_KOLOM) + pemetaan manual di UI.
"""
import hashlib
import io
import re

import pandas as pd

from . import config
from .parsing import deteksi_mode_m, parse_angka, persen_ke_angka


def _norm(teks: str) -> str:
    """Header -> huruf kecil, tanpa tanda baca, spasi tunggal."""
    t = str(teks).lower()
    t = re.sub(r"\(.*?\)", " ", t)          # buang "(Rp)", "(7d)", dst
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def baca_file(file_obj, nama_file: str = "") -> pd.DataFrame:
    """Baca CSV (deteksi pemisah & encoding) atau Excel menjadi DataFrame mentah."""
    nama = (nama_file or getattr(file_obj, "name", "")).lower()
    data = file_obj.read() if hasattr(file_obj, "read") else open(file_obj, "rb").read()
    if nama.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(data), dtype=str)
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            teks = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    # sep=None + engine python = deteksi otomatis koma / titik koma / tab
    return pd.read_csv(io.StringIO(teks), sep=None, engine="python", dtype=str)


def tebak_pemetaan(kolom_mentah) -> dict:
    """
    Kembalikan {kolom_internal: kolom_mentah}. Cocok persis dulu, lalu
    'mengandung' (misal "Revenue(Rp) 7D" mengandung "revenue").
    """
    hasil, terpakai = {}, set()
    norm = {k: _norm(k) for k in kolom_mentah}
    alias = {i: [_norm(a) for a in lst] for i, lst in config.ALIAS_KOLOM.items()}
    # Putaran 1: cocok persis untuk SEMUA kolom dulu (paling bisa dipercaya)
    for internal, alias_norm in alias.items():
        for k, n in norm.items():
            if k not in terpakai and n in alias_norm:
                hasil[internal] = k
                terpakai.add(k)
                break
    # Putaran 2: header diawali alias, alias terpanjang dulu agar lebih spesifik
    for internal, alias_norm in alias.items():
        if internal in hasil:
            continue
        for a in sorted(alias_norm, key=len, reverse=True):
            cocok = [k for k, n in norm.items() if k not in terpakai and n.startswith(a)]
            if cocok:
                hasil[internal] = cocok[0]
                terpakai.add(cocok[0])
                break
    return hasil


def _id_dari_url(url) -> str | None:
    m = re.search(r"(\d{12,})", str(url or ""))
    return m.group(1) if m else None


def normalisasi(df_mentah: pd.DataFrame, pemetaan: dict) -> tuple[pd.DataFrame, list[str]]:
    """
    Ubah DataFrame mentah menjadi skema internal + daftar peringatan.
    Tidak ada baris yang dibuang diam-diam: baris rusak tetap ada, nilai NaN,
    dan akan gagal di filter dengan alasan yang terbaca.
    """
    peringatan = []
    df = pd.DataFrame(index=df_mentah.index)
    for internal, sumber in pemetaan.items():
        if sumber and sumber in df_mentah.columns:
            df[internal] = df_mentah[sumber]

    hilang = [k for k in config.KOLOM_WAJIB if k not in df.columns]
    if hilang:
        peringatan.append(f"Kolom wajib belum terpetakan: {', '.join(hilang)}")

    # Kolom uang: deteksi format (jt/rb -> M berarti miliar)
    for kol in ("harga", "omzet_7h", "omzet_sebelumnya"):
        if kol in df.columns:
            mode = deteksi_mode_m(df[kol].tolist())
            df[kol] = df[kol].map(lambda v: parse_angka(v, mode)).astype(float)
    for kol in ("jumlah_creator", "terjual_7h", "jumlah_video"):
        if kol in df.columns:
            mode = deteksi_mode_m(df[kol].tolist())
            df[kol] = df[kol].map(lambda v: parse_angka(v, mode)).astype(float)
    for kol in ("komisi_pct", "pertumbuhan_pct"):
        if kol in df.columns:
            df[kol] = persen_ke_angka(df[kol])

    # Pertumbuhan: kalau tidak ada di export tapi ada omzet periode sebelumnya, hitung.
    if "pertumbuhan_pct" not in df.columns:
        if "omzet_sebelumnya" in df.columns:
            prev = df["omzet_sebelumnya"].where(df["omzet_sebelumnya"] > 0)
            df["pertumbuhan_pct"] = (df["omzet_7h"] / prev - 1.0) * 100.0
            peringatan.append("Pertumbuhan dihitung dari kolom omzet periode sebelumnya.")
        else:
            df["pertumbuhan_pct"] = float("nan")
            peringatan.append("Export tidak punya kolom pertumbuhan. Akan dicoba dari "
                              "snapshot minggu lalu (lihat menu Riwayat).")

    # Gabungkan teks kategori level 1/2/3 agar pencocokan kata kunci lebih kaya
    teks_kat = [df[k].fillna("").astype(str) for k in ("kategori", "kategori2", "kategori3")
                if k in df.columns]
    df["kategori_teks"] = (pd.concat(teks_kat, axis=1).agg(" / ".join, axis=1)
                           if teks_kat else "")

    for kol in ("nama", "toko", "url_produk"):
        if kol not in df.columns:
            df[kol] = ""
        df[kol] = df[kol].fillna("").astype(str).str.strip()

    # ID produk stabil: dari kolom ID, lalu dari URL, lalu hash nama+toko.
    if "produk_id" in df.columns:
        df["produk_id"] = df["produk_id"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
    else:
        df["produk_id"] = ""
    kosong = df["produk_id"].str.strip() == ""
    df.loc[kosong, "produk_id"] = df.loc[kosong, "url_produk"].map(_id_dari_url)
    kosong = df["produk_id"].isna() | (df["produk_id"].astype(str).str.strip() == "")
    df.loc[kosong, "produk_id"] = (df.loc[kosong, "nama"] + "|" + df.loc[kosong, "toko"]).map(
        lambda s: "h" + hashlib.md5(s.encode()).hexdigest()[:12])

    dup = df["produk_id"].duplicated().sum()
    if dup:
        peringatan.append(f"{dup} baris duplikat (produk sama) dibuang — export ganda halaman?")
        df = df.drop_duplicates("produk_id", keep="first")

    return df.reset_index(drop=True), peringatan

