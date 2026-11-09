"""
trend.py — Deteksi TIMING TREN: lewat puncak & lonjakan persaingan creator.

Masalah: satu export Kalodata hanya memotret 1 periode. Produk bisa lolos
filter (+20% growth) padahal minggu ini sudah melambat, atau creator naik
2x lipat sehingga jatah views per creator anjlok.

Solusi: setiap impor disimpan sebagai SNAPSHOT bertanggal. Mulai impor kedua
(idealnya 7 hari kemudian, sesuai ritme mingguan blueprint) modul
membandingkan angka sekarang vs snapshot sebelumnya.

Bendera (flag) yang dihasilkan:
- lewat_puncak     : omzet turun >=10% vs snapshot lalu, ATAU pertumbuhan
                     melambat >50% dari pertumbuhan sebelumnya (yang >=40%)
- creator_melonjak : creator naik >=50% DAN lebih cepat dari omzet (+20 poin)
- kompetisi_padat  : creator >= 80% dari batas maksimum filter (1 snapshot cukup)
- lonjakan_ekstrem : pertumbuhan >300% (sering viral sesaat; cek manual)
- belum_ada_riwayat: info saja, bukan penalti
"""
import pandas as pd

from . import config

JEDA_MIN_HARI = 3     # snapshot pembanding minimal 3 hari lebih lama
JEDA_GROWTH = (5, 9)  # rentang jeda yang sah untuk MENGHITUNG growth 7 hari


def _pembanding(tanggal: str, riwayat: pd.DataFrame) -> pd.DataFrame:
    """Ambil baris snapshot terbaru per produk yang >= JEDA_MIN_HARI lebih lama."""
    if riwayat.empty:
        return riwayat
    r = riwayat.copy()
    r["_tgl"] = pd.to_datetime(r["tanggal"])
    batas = pd.to_datetime(tanggal) - pd.Timedelta(days=JEDA_MIN_HARI)
    r = r[r["_tgl"] <= batas]
    if r.empty:
        return r
    r = r.sort_values("_tgl").groupby("produk_id").tail(1)
    r["jeda_hari"] = (pd.to_datetime(tanggal) - r["_tgl"]).dt.days
    return r.drop(columns="_tgl")


def analisis_tren(df: pd.DataFrame, tanggal: str, riwayat: pd.DataFrame,
                  creator_max: float) -> pd.DataFrame:
    """Tambahkan kolom tren & 'flag_tren' (list string) ke df."""
    out = df.copy()
    prev = _pembanding(tanggal, riwayat)
    kol_prev = ["produk_id", "omzet_7h", "jumlah_creator", "pertumbuhan_pct", "jeda_hari"]
    if prev.empty:
        for k in kol_prev[1:]:
            out[f"{k}_lalu"] = float("nan")
    else:
        out = out.merge(prev[kol_prev].add_suffix("_lalu").rename(
            columns={"produk_id_lalu": "produk_id"}), on="produk_id", how="left")

    out["sumber_growth"] = out["pertumbuhan_pct"].notna().map({True: "export", False: ""})
    # Isi growth yang kosong dari snapshot ~7 hari lalu
    bisa = (out["pertumbuhan_pct"].isna() & out["omzet_7h_lalu"].gt(0)
            & out["jeda_hari_lalu"].between(*JEDA_GROWTH))
    out.loc[bisa, "pertumbuhan_pct"] = (out.loc[bisa, "omzet_7h"] / out.loc[bisa, "omzet_7h_lalu"] - 1) * 100
    out.loc[bisa, "sumber_growth"] = "snapshot"

    d_omzet = out["omzet_7h"] / out["omzet_7h_lalu"] - 1
    d_creator = out["jumlah_creator"] / out["jumlah_creator_lalu"] - 1
    out["delta_omzet_pct"] = (d_omzet * 100).round(1)
    out["delta_creator_pct"] = (d_creator * 100).round(1)

    def flags(i):
        r = out.loc[i]
        f = []
        if pd.isna(r["omzet_7h_lalu"]):
            f.append("belum_ada_riwayat")
        else:
            gp = r["pertumbuhan_pct_lalu"]
            if d_omzet[i] <= -0.10 or (pd.notna(gp) and gp >= 40 and pd.notna(r["pertumbuhan_pct"])
                                       and r["pertumbuhan_pct"] < gp * 0.5):
                f.append("lewat_puncak")
            if pd.notna(d_creator[i]) and d_creator[i] >= 0.5 and d_creator[i] > (d_omzet[i] + 0.2):
                f.append("creator_melonjak")
        if pd.notna(r["jumlah_creator"]) and r["jumlah_creator"] >= 0.8 * creator_max:
            f.append("kompetisi_padat")
        if pd.notna(r["pertumbuhan_pct"]) and r["pertumbuhan_pct"] > 300:
            f.append("lonjakan_ekstrem")
        return f

    out["flag_tren"] = [flags(i) for i in out.index]
    out["penalti_tren"] = out["flag_tren"].map(
        lambda fl: sum(config.PENALTI_TREN.get(x, 0) for x in fl))
    return out
