"""
scoring.py — Skor 0–100 dari 3 komponen: komisi, pertumbuhan, kepadatan creator.

Risiko: TIMING TREN. Kepadatan = omzet 7 hari / jumlah creator.
Contoh: Rp60 jt dibagi 20 creator = Rp3 jt/creator (masih longgar),
        Rp60 jt dibagi 140 creator = Rp430 rb/creator (sudah padat).

Skala absolut (config.SKALA_SKOR), bukan peringkat relatif, agar skor
antar-minggu bisa dibandingkan. Kepadatan memakai skala log karena
rentangnya lebar (ratusan ribu s/d jutaan).
"""
import math

import pandas as pd

from . import config


def _linear(x, lo, hi):
    if pd.isna(x):
        return 0.0
    return max(0.0, min(100.0, (x - lo) / (hi - lo) * 100.0))


def _log(x, lo, hi):
    if pd.isna(x) or x <= 0:
        return 0.0
    return max(0.0, min(100.0, (math.log10(x) - math.log10(lo)) /
                        (math.log10(hi) - math.log10(lo)) * 100.0))


def beri_skor(df: pd.DataFrame, bobot: dict | None = None) -> pd.DataFrame:
    b = bobot or config.BOBOT_SKOR
    total_b = sum(b.values()) or 1.0
    s = config.SKALA_SKOR
    out = df.copy()
    out["omzet_per_creator"] = out["omzet_7h"] / out["jumlah_creator"].where(out["jumlah_creator"] > 0)
    out["skor_komisi"] = out["komisi_pct"].map(lambda x: _linear(x, *s["komisi"])).round(1)
    out["skor_pertumbuhan"] = out["pertumbuhan_pct"].map(lambda x: _linear(x, *s["pertumbuhan"])).round(1)
    out["skor_kepadatan"] = out["omzet_per_creator"].map(lambda x: _log(x, *s["kepadatan"])).round(1)
    out["skor_dasar"] = ((out["skor_komisi"] * b["komisi"] + out["skor_pertumbuhan"] * b["pertumbuhan"]
                          + out["skor_kepadatan"] * b["kepadatan"]) / total_b).round(1)
    pen = out["penalti_tren"] if "penalti_tren" in out else 0
    out["skor_akhir"] = (out["skor_dasar"] - pen).clip(lower=0).round(1)
    return out
