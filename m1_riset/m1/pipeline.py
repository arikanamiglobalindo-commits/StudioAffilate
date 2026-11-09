"""
pipeline.py — Urutan proses satu kali run M1:

  export Kalodata -> normalisasi -> snapshot & tren -> 6 filter -> skor

Urutan ini disengaja: tren dihitung SEBELUM filter karena snapshot bisa
mengisi data pertumbuhan yang kosong di export.
"""
import pandas as pd

from . import db
from .filters import terapkan_filter
from .scoring import beri_skor
from .trend import analisis_tren


def jalankan(df_norm: pd.DataFrame, tanggal_data: str, filter_nilai: dict,
             kategori_aktif: dict, bobot: dict | None = None,
             simpan: bool = True, db_path=None) -> pd.DataFrame:
    riwayat = db.baca_snapshot(db_path)
    # Jangan bandingkan dengan snapshot di tanggal yang sama (impor ulang)
    riwayat = riwayat[riwayat["tanggal"] != tanggal_data]
    df = analisis_tren(df_norm, tanggal_data, riwayat, filter_nilai["creator_max"])
    if simpan:
        db.simpan_snapshot(df, tanggal_data, db_path)
    df = terapkan_filter(df, filter_nilai, kategori_aktif)
    return beri_skor(df, bobot)
