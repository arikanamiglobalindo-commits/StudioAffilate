"""
footage.py — Mencari, memvalidasi, dan memetakan footage ke 4 adegan.

Risiko: HAK FOOTAGE.

KEPUTUSAN TEKNIS:
1) Tidak ada API resmi untuk "daftar semua video seller untuk produk X".
   Scraping TikTok/Kalodata melanggar ToS. Jadi pencarian dibuat
   SEMI-OTOMATIS: modul membuat link pencarian yang sudah terarah
   (profil seller, pencarian TikTok, halaman produk), Anda menempel URL video.
2) Kepemilikan video dicek OTOMATIS lewat endpoint resmi TikTok oEmbed
   (https://www.tiktok.com/oembed) — endpoint publik untuk embed, bukan
   scraping. Handle pemilik dibandingkan dengan handle resmi seller.
3) Timestamp adegan diisi manual (mm:ss). Mesin tidak bisa menilai "ini
   adegan masalah" dengan andal tanpa AI berbayar; manual = akurat & murah.
4) Klip dibatasi 1–15 detik per adegan dan diambil dari beberapa sumber:
   membuat video Anda hasil suntingan baru, bukan re-upload utuh
   (kebijakan TikTok: konten tanpa perubahan kreatif tidak masuk FYP).
"""
import re
from urllib.parse import quote_plus

import pandas as pd
import requests

from . import config

_RE_HANDLE = re.compile(r"tiktok\.com/@([A-Za-z0-9._]+)", re.IGNORECASE)
URUTAN_HAK = {"seller_izin": 0, "seller": 1, "affiliate_berisiko": 2}


def normal_handle(h: str) -> str:
    return str(h or "").strip().lstrip("@").lower()


def handle_dari_url(url: str) -> str:
    m = _RE_HANDLE.search(str(url or ""))
    return normal_handle(m.group(1)) if m else ""


def ambil_oembed(url: str, timeout: float = 10.0) -> dict:
    """
    Panggil TikTok oEmbed resmi. Mengembalikan {"handle", "judul", "thumbnail", "error"}.
    Juga bekerja untuk link pendek vt.tiktok.com / vm.tiktok.com.
    """
    try:
        r = requests.get("https://www.tiktok.com/oembed", params={"url": url}, timeout=timeout)
        if r.status_code != 200:
            return {"handle": handle_dari_url(url), "judul": "", "thumbnail": "",
                    "error": f"oEmbed HTTP {r.status_code} (video privat/dihapus?)"}
        j = r.json()
        return {"handle": handle_dari_url(j.get("author_url", "")) or handle_dari_url(url),
                "judul": j.get("title", ""), "thumbnail": j.get("thumbnail_url", ""), "error": ""}
    except (requests.RequestException, ValueError) as e:
        return {"handle": handle_dari_url(url), "judul": "", "thumbnail": "",
                "error": f"oEmbed gagal: {e.__class__.__name__}"}


def daftar_handle(teks: str) -> set[str]:
    """'@tokoA, tokoA.official' -> {'tokoa', 'tokoa.official'}"""
    return {normal_handle(x) for x in re.split(r"[,\s;]+", str(teks or "")) if x.strip()}


def tentukan_status_hak(handle_video: str, handle_seller: set[str], bukti_izin: str = "") -> str:
    """
    seller_izin        : video milik akun resmi seller DAN ada bukti izin (link chat/screenshot)
    seller             : video milik akun resmi seller, izin belum dicatat
    affiliate_berisiko : selain itu (termasuk handle tidak diketahui) -> cadangan saja
    """
    if handle_video and normal_handle(handle_video) in handle_seller:
        return "seller_izin" if str(bukti_izin or "").strip() else "seller"
    return "affiliate_berisiko"


def validasi_klip(mulai: float, selesai: float) -> list[str]:
    err = []
    if pd.isna(mulai) or pd.isna(selesai):
        return ["timestamp mulai/selesai wajib diisi (format mm:ss)"]
    if selesai <= mulai:
        err.append("selesai harus lebih besar dari mulai")
    dur = selesai - mulai
    if dur < config.DURASI_ADEGAN_MIN:
        err.append(f"durasi {dur:.1f}s terlalu pendek (min {config.DURASI_ADEGAN_MIN}s)")
    if dur > config.DURASI_ADEGAN_MAX:
        err.append(f"durasi {dur:.1f}s terlalu panjang (maks {config.DURASI_ADEGAN_MAX}s) "
                   "— potong agar tidak dianggap re-upload")
    return err


def link_pencarian(nama: str, toko: str, handle_seller: set[str], url_produk: str = "") -> dict:
    """Link terarah untuk berburu footage — urutan = prioritas (seller dulu)."""
    kata = " ".join(str(nama).split()[:6])  # 6 kata pertama cukup spesifik
    links = {}
    for h in sorted(handle_seller):
        links[f"1. Profil seller @{h}"] = f"https://www.tiktok.com/@{h}"
    if url_produk:
        links["2. Halaman produk (tab Video)"] = url_produk
    links["3. Cari di TikTok: nama toko + produk"] = (
        "https://www.tiktok.com/search/video?q=" + quote_plus(f"{toko} {kata}"))
    links["4. Cari di TikTok: nama produk (affiliate = cadangan)"] = (
        "https://www.tiktok.com/search/video?q=" + quote_plus(kata))
    return links


def ringkas_kelengkapan(footage: pd.DataFrame, produk_ids) -> pd.DataFrame:
    """
    Per produk: status hak terbaik per adegan, jumlah adegan terisi,
    jumlah adegan dari seller, dan apakah lolos syarat gerbang (>= 3 seller).
    """
    baris = []
    for pid in produk_ids:
        sub = footage[footage["produk_id"] == pid] if len(footage) else footage
        rec = {"produk_id": pid}
        n_isi = n_seller = 0
        for adg in config.ADEGAN:
            s = sub[sub["adegan"] == adg] if len(sub) else sub
            if len(s):
                terbaik = min(s["status_hak"], key=lambda x: URUTAN_HAK.get(x, 9))
                rec[f"adegan_{adg}"] = terbaik
                n_isi += 1
                n_seller += terbaik in config.STATUS_SELLER
            else:
                rec[f"adegan_{adg}"] = "KOSONG"
        rec["adegan_terisi"] = n_isi
        rec["adegan_seller"] = n_seller
        rec["footage_lengkap_4"] = n_isi == len(config.ADEGAN)
        rec["lolos_syarat_footage"] = n_seller >= config.MIN_ADEGAN_SELLER
        baris.append(rec)
    return pd.DataFrame(baris)


def klip_terpilih(footage: pd.DataFrame, produk_id: str) -> list[dict]:
    """Klip terbaik per adegan (seller_izin > seller > affiliate) untuk dikirim ke n8n/VEO3."""
    hasil = []
    sub = footage[footage["produk_id"] == produk_id]
    for adg in config.ADEGAN:
        s = sub[sub["adegan"] == adg].copy()
        if s.empty:
            continue
        s["_urut"] = s["status_hak"].map(lambda x: URUTAN_HAK.get(x, 9))
        r = s.sort_values(["_urut", "id"]).iloc[0]
        hasil.append({
            "adegan": adg, "url": r["url"], "mulai_detik": float(r["mulai"]),
            "selesai_detik": float(r["selesai"]), "creator": r["creator_handle"],
            "status_hak": r["status_hak"], "bukti_izin": r["bukti_izin"] or "",
            "berisiko": r["status_hak"] == "affiliate_berisiko",
        })
    return hasil
