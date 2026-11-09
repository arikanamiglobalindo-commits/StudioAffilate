"""
filters.py — Enam filter + penentuan kategori.

Risiko yang ditangani: TIMING TREN (pertumbuhan & jumlah creator) dan
kualitas data (baris tanpa angka gagal dengan alasan jelas, bukan lolos diam-diam).

Setiap produk mendapat kolom lolos_<filter> dan 'alasan_gagal' agar Anda
bisa melihat KENAPA produk dibuang — penting untuk menyetel filter dengan sadar.
"""
import re

import pandas as pd

from . import config


def tentukan_kategori(df: pd.DataFrame, kategori_aktif: dict) -> pd.Series:
    """
    Kembalikan nama kategori blueprint yang cocok, atau "" bila tidak cocok.
    1) Data dari API membawa 'kategori_label' (mis. "Rumah Tangga - dapur") -> dipakai langsung.
    2) Selain itu: kata kunci dicari sebagai KATA UTUH (boleh jamak -s) pada teks
       kategori + nama produk. Kata utuh mencegah "pel" cocok dengan "Perlengkapan".
    """
    pola = {nama: re.compile(r"\b(" + "|".join(re.escape(k.strip()) for k in kunci) + r")s?\b", re.I)
            for nama, kunci in kategori_aktif.items()}
    label = df["kategori_label"].fillna("") if "kategori_label" in df else pd.Series("", index=df.index)
    teks = (df["kategori_teks"].fillna("") + " | " + df["nama"].fillna("")).str.lower()

    def cocok(lbl, t):
        if lbl:
            for nama in kategori_aktif:
                if lbl == nama or lbl.startswith(nama + " - "):
                    return nama
            return ""
        for nama, rx in pola.items():
            if rx.search(t):
                return nama
        return ""
    return pd.Series([cocok(a, b) for a, b in zip(label, teks)], index=df.index)


def rata_komisi_kategori_opsional(df: pd.DataFrame) -> pd.DataFrame:
    """
    Hitung rata-rata komisi tiap kategori opsional pada SELURUH data impor
    (sebelum filter). Kategori hanya boleh diaktifkan bila >= ambang 10%.
    """
    baris = []
    for nama, kunci in config.KATEGORI_OPSIONAL.items():
        kat = tentukan_kategori(df, {nama: kunci})
        sub = df[kat == nama]
        rata = sub["komisi_pct"].mean() if len(sub) else float("nan")
        baris.append({
            "kategori": nama,
            "jumlah_produk": len(sub),
            "rata_komisi_pct": round(rata, 2) if pd.notna(rata) else None,
            "boleh_diaktifkan": bool(pd.notna(rata) and rata >= config.AMBANG_KOMISI_TAMBAHAN
                                     and len(sub) >= 5),
        })
    return pd.DataFrame(baris)


def terapkan_filter(df: pd.DataFrame, f: dict, kategori_aktif: dict) -> pd.DataFrame:
    """Tambahkan kolom per-filter + 'lolos' + 'alasan_gagal'."""
    out = df.copy()
    out["kategori_m1"] = tentukan_kategori(out, kategori_aktif)

    def antara(kol, lo, hi):
        return out[kol].between(lo, hi) if kol in out else pd.Series(False, index=out.index)

    out["lolos_harga"] = antara("harga", f["harga_min"], f["harga_max"])
    out["lolos_omzet"] = antara("omzet_7h", f["omzet7_min"], f["omzet7_max"])
    out["lolos_growth"] = out["pertumbuhan_pct"] >= f["growth_min"]   # NaN -> False
    out["lolos_creator"] = antara("jumlah_creator", f["creator_min"], f["creator_max"])
    out["lolos_komisi"] = out["komisi_pct"] >= f["komisi_min"]
    out["lolos_kategori"] = out["kategori_m1"] != ""

    label = {
        "lolos_harga": lambda r: f"harga {r.get('harga'):,.0f} di luar rentang",
        "lolos_omzet": lambda r: f"omzet 7h {r.get('omzet_7h'):,.0f} di luar rentang",
        "lolos_growth": lambda r: ("data pertumbuhan tidak ada" if pd.isna(r.get("pertumbuhan_pct"))
                                   else f"pertumbuhan {r.get('pertumbuhan_pct'):.1f}% < minimum"),
        "lolos_creator": lambda r: f"creator {r.get('jumlah_creator'):.0f} di luar rentang",
        "lolos_komisi": lambda r: f"komisi {r.get('komisi_pct'):.1f}% < minimum",
        "lolos_kategori": lambda r: "kategori di luar blueprint",
    }

    def alasan(r):
        hasil = []
        for kol, fn in label.items():
            if not r[kol]:
                try:
                    hasil.append(fn(r))
                except (TypeError, ValueError):
                    hasil.append(kol.replace("lolos_", "") + ": data kosong/rusak")
        return "; ".join(hasil)

    kol_filter = list(label)
    out["lolos"] = out[kol_filter].all(axis=1)
    out["alasan_gagal"] = out.apply(alasan, axis=1)
    return out


def corong(df_filter: pd.DataFrame) -> pd.DataFrame:
    """Corong bertahap: berapa produk tersisa setelah tiap filter (urutan tetap)."""
    urutan = [("Total impor", None), ("Kategori", "lolos_kategori"), ("Harga", "lolos_harga"),
              ("Omzet 7 hari", "lolos_omzet"), ("Komisi", "lolos_komisi"),
              ("Jumlah creator", "lolos_creator"), ("Pertumbuhan", "lolos_growth")]
    mask = pd.Series(True, index=df_filter.index)
    baris = []
    for nama, kol in urutan:
        if kol:
            mask &= df_filter[kol]
        baris.append({"tahap": nama, "tersisa": int(mask.sum()),
                      "gagal_di_filter_ini_saja": int((~df_filter[kol]).sum()) if kol else 0})
    return pd.DataFrame(baris)
