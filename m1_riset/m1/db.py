"""
db.py — Penyimpanan lokal SQLite (satu file: data/m1.db).

Kenapa SQLite? Bawaan Python (tanpa install server), satu file yang mudah
di-backup, dan cukup untuk ribuan produk. Dipakai untuk:
- snapshot   : riwayat angka produk per tanggal impor  -> deteksi Timing Tren
- footage    : 4 adegan per produk + link + timestamp + status hak -> Hak Footage
- seller     : handle TikTok resmi tiap toko -> klasifikasi seller vs affiliate
- terkirim   : catatan produk yang sudah dikirim ke n8n -> cegah kirim ganda
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pandas as pd

# Bisa diganti lewat variabel lingkungan M1_DB (dipakai untuk mode demo/tes)
DB_PATH = Path(os.environ.get("M1_DB") or Path(__file__).resolve().parent.parent / "data" / "m1.db")

SKEMA = """
CREATE TABLE IF NOT EXISTS snapshot (
    tanggal TEXT, produk_id TEXT, nama TEXT, toko TEXT,
    omzet_7h REAL, jumlah_creator REAL, pertumbuhan_pct REAL,
    komisi_pct REAL, harga REAL,
    PRIMARY KEY (tanggal, produk_id)
);
CREATE TABLE IF NOT EXISTS footage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    produk_id TEXT, adegan TEXT, url TEXT,
    mulai REAL, selesai REAL,
    creator_handle TEXT, status_hak TEXT,
    bukti_izin TEXT, catatan TEXT, dibuat TEXT,
    UNIQUE (produk_id, adegan, url, mulai)
);
CREATE TABLE IF NOT EXISTS seller (
    toko TEXT PRIMARY KEY, handle TEXT
);
CREATE TABLE IF NOT EXISTS terkirim (
    kunci TEXT PRIMARY KEY, produk_id TEXT, tanggal_data TEXT,
    dikirim_pada TEXT, respon TEXT
);
"""


@contextmanager
def koneksi(path: Path | str | None = None):
    p = Path(path or DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.executescript(SKEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()


# ---------------- snapshot ----------------
def simpan_snapshot(df: pd.DataFrame, tanggal: str, path=None) -> int:
    kol = ["produk_id", "nama", "toko", "omzet_7h", "jumlah_creator",
           "pertumbuhan_pct", "komisi_pct", "harga"]
    data = df.reindex(columns=kol).copy()
    data.insert(0, "tanggal", tanggal)
    with koneksi(path) as con:
        con.execute("DELETE FROM snapshot WHERE tanggal = ?", (tanggal,))
        data.to_sql("snapshot", con, if_exists="append", index=False)
    return len(data)


def baca_snapshot(path=None) -> pd.DataFrame:
    with koneksi(path) as con:
        return pd.read_sql("SELECT * FROM snapshot", con)


def daftar_tanggal_snapshot(path=None) -> list[str]:
    with koneksi(path) as con:
        return [r[0] for r in con.execute("SELECT DISTINCT tanggal FROM snapshot ORDER BY tanggal")]


# ---------------- seller ----------------
def set_handle_seller(toko: str, handle: str, path=None):
    with koneksi(path) as con:
        con.execute("INSERT OR REPLACE INTO seller VALUES (?, ?)", (toko, handle))


def peta_handle_seller(path=None) -> dict:
    with koneksi(path) as con:
        return {t: h for t, h in con.execute("SELECT toko, handle FROM seller")}


# ---------------- footage ----------------
def tambah_footage(row: dict, path=None):
    row = {**row, "dibuat": datetime.now().isoformat(timespec="seconds")}
    kol = ["produk_id", "adegan", "url", "mulai", "selesai", "creator_handle",
           "status_hak", "bukti_izin", "catatan", "dibuat"]
    with koneksi(path) as con:
        con.execute(f"INSERT OR REPLACE INTO footage ({','.join(kol)}) VALUES ({','.join('?' * len(kol))})",
                    [row.get(k) for k in kol])


def hapus_footage(footage_id: int, path=None):
    with koneksi(path) as con:
        con.execute("DELETE FROM footage WHERE id = ?", (footage_id,))


def baca_footage(produk_id: str | None = None, path=None) -> pd.DataFrame:
    with koneksi(path) as con:
        if produk_id:
            return pd.read_sql("SELECT * FROM footage WHERE produk_id = ? ORDER BY adegan, id",
                               con, params=(produk_id,))
        return pd.read_sql("SELECT * FROM footage ORDER BY produk_id, adegan, id", con)


# ---------------- terkirim ----------------
def sudah_terkirim(kunci: str, path=None) -> bool:
    with koneksi(path) as con:
        return con.execute("SELECT 1 FROM terkirim WHERE kunci = ?", (kunci,)).fetchone() is not None


def catat_terkirim(kunci: str, produk_id: str, tanggal_data: str, respon: str, path=None):
    with koneksi(path) as con:
        con.execute("INSERT OR REPLACE INTO terkirim VALUES (?, ?, ?, ?, ?)",
                    (kunci, produk_id, tanggal_data,
                     datetime.now().isoformat(timespec="seconds"), respon[:500]))
