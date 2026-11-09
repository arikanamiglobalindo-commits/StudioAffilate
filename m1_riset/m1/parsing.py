"""
parsing.py — Mengubah teks angka gaya Kalodata/Indonesia menjadi float.

Risiko: AKSES DATA (data salah baca = filter salah = produk salah).
Contoh yang ditangani:
    "Rp1,23jt" -> 1_230_000        "Rp 950rb" -> 950_000
    "Rp15.2M"  -> 15_200_000 (mode Inggris, M = million)
    "Rp1,2M"   -> 1_200_000_000 (mode Indonesia, M = miliar)
    "Rp 1.234.567" -> 1_234_567    "12,5%" -> 12.5     "+20%" -> 20.0
    "Rp50.000 - Rp75.000" -> 62_500 (rentang harga -> nilai tengah)
    "-", "", "N/A" -> NaN
"""
import math
import re

KOSONG = {"", "-", "--", "n/a", "na", "none", "null", "nan", "—"}

# Pengali sufiks. 'm' bergantung mode (lihat parse_angka).
_SUFIKS_ID = {"rb": 1e3, "ribu": 1e3, "k": 1e3, "jt": 1e6, "juta": 1e6,
              "m": 1e9, "miliar": 1e9, "milyar": 1e9, "t": 1e12}
_SUFIKS_EN = {"k": 1e3, "rb": 1e3, "jt": 1e6, "m": 1e6, "mn": 1e6, "b": 1e9, "bn": 1e9}

_RE_ANGKA = re.compile(r"([+-]?\d[\d.,]*)\s*(rb|ribu|jt|juta|miliar|milyar|mn|bn|k|m|b|t)?\b",
                       re.IGNORECASE)


def _normalisasi_pemisah(s: str, boleh_ribuan: bool = True) -> float:
    """Tentukan mana pemisah ribuan dan mana desimal, lalu ubah ke float.
    boleh_ribuan=False: "1.414" dibaca 1,414 (desimal), dipakai untuk persen & angka bersufiks."""
    s = s.strip().lstrip("+")
    neg = s.startswith("-")
    s = s.lstrip("-")
    if "," in s and "." in s:
        # Yang muncul terakhir = desimal. "1.234,5" (ID) atau "1,234.5" (EN)
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        bagian = s.split(sep)
        # Pola ribuan: 1.234 / 12.345.678 (semua grup setelah pertama = 3 digit)
        if len(bagian) > 2 or (boleh_ribuan and len(bagian) == 2 and len(bagian[1]) == 3
                               and len(bagian[0]) <= 3 and bagian[0] != "0"):
            s = "".join(bagian)
        else:
            s = bagian[0] + "." + bagian[1]
    nilai = float(s) if s else math.nan
    return -nilai if neg else nilai


def parse_angka(nilai, mode_m: str = "en", boleh_ribuan: bool = True) -> float:
    """
    Ubah satu nilai menjadi float.
    mode_m: "en" -> M = juta (million), "id" -> M = miliar.
    Untuk rentang ("a - b" atau "a ~ b") dikembalikan nilai tengahnya.
    """
    if nilai is None:
        return math.nan
    if isinstance(nilai, (int, float)):
        return float(nilai) if not (isinstance(nilai, float) and math.isnan(nilai)) else math.nan
    teks = str(nilai).strip().lower()
    if teks in KOSONG:
        return math.nan
    teks = teks.replace("rp", "").replace("idr", "").replace("%", "").replace(" ", " ")
    # Pisahkan rentang. Tanda '-' di awal = negatif, bukan rentang.
    potongan = re.split(r"\s*(?:~|–|—|\bs/d\b|\bto\b|(?<=[\d a-z])\s*-\s*(?=\d))\s*", teks)
    tabel = _SUFIKS_ID if mode_m == "id" else _SUFIKS_EN
    hasil = []
    for p in potongan:
        p = re.sub(r"(\d)\s+(?=[a-z])", r"\1", p.strip())  # "15,2 jt" -> "15,2jt"
        m = _RE_ANGKA.search(p)
        if not m:
            continue
        suf = (m.group(2) or "").lower()
        # Angka bersufiks ("3.170M") tidak mungkin memakai pemisah ribuan
        angka = _normalisasi_pemisah(m.group(1), boleh_ribuan and not suf)
        hasil.append(angka * tabel.get(suf, 1.0))
    if not hasil:
        return math.nan
    return sum(hasil) / len(hasil)


def deteksi_mode_m(nilai_kolom) -> str:
    """Kalau di kolom ada 'jt'/'rb'/'juta' -> format Indonesia (M = miliar)."""
    for v in nilai_kolom:
        if isinstance(v, str) and re.search(r"\d\s*(jt|rb|juta|ribu)\b", v.lower()):
            return "id"
    return "en"


def persen_ke_angka(seri):
    """
    Kolom persen bisa berupa '12,5%' (sudah persen) atau 0.125 (pecahan).
    Aturan: kalau TIDAK ada tanda % di kolom dan median |nilai| <= 1, anggap pecahan -> x100.
    """
    import pandas as pd
    ada_persen = seri.astype(str).str.contains("%").any()
    angka = seri.map(lambda v: parse_angka(v, boleh_ribuan=False)).astype(float)
    if not ada_persen:
        med = angka.abs().median()
        if pd.notna(med) and med <= 1.0:
            angka = angka * 100.0
    return angka


def parse_timestamp(teks) -> float:
    """'0:05' -> 5.0, '1:02.5' -> 62.5, '7' -> 7.0, '' -> NaN."""
    if teks is None:
        return math.nan
    t = str(teks).strip().replace(",", ".")
    if not t:
        return math.nan
    try:
        bagian = [float(x) for x in t.split(":")]
    except ValueError:
        return math.nan
    detik = 0.0
    for b in bagian:
        detik = detik * 60 + b
    return detik


def format_rupiah(x) -> str:
    """Tampilan ringkas: 15_200_000 -> 'Rp15,2 jt'."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    if abs(x) >= 1e9:
        return f"Rp{x / 1e9:.2f} M".replace(".", ",")
    if abs(x) >= 1e6:
        return f"Rp{x / 1e6:.1f} jt".replace(".", ",")
    if abs(x) >= 1e3:
        return f"Rp{x / 1e3:.0f} rb"
    return f"Rp{x:.0f}"
