"""
sumber_api.py — Menarik data tab Produk lewat Kalodata Open API lalu mengubahnya
ke skema yang sama dengan hasil importer.normalisasi(). Dengan begitu filter,
tren, skor, footage, dan gerbang TIDAK perlu diubah.

Risiko: AKSES DATA (+ biaya kredit).

Alur hemat kredit:
  1) Cari ID kategori sekali saja (disimpan di data/kategori_api.json)
  2) Ranking produk per kategori (1 panggilan = 100 produk), urut pertumbuhan omzet
  3) Saring LOKAL dengan field yang sudah ada di ranking (harga, omzet, growth,
     komisi). Hanya kandidat yang lolos yang dipanggil detailnya.
  4) Detail produk -> shop_id (+ jumlah creator bila tersedia)
  5) Jumlah creator: kalau detail tidak memberi angka, hitung dari ranking
     creator per produk (maks 2 halaman = cukup untuk batas 150)
  6) Nama toko: detail toko, 1 panggilan per toko unik
"""
import json
import math
import re
from pathlib import Path

import pandas as pd

from . import config, db
from .kalodata_api import KalodataAPI, KalodataError

# Disimpan di folder yang sama dengan database (ikut variabel M1_DB saat uji)
FILE_KATEGORI = Path(db.DB_PATH).parent / "kategori_api.json"


# ------------------------------------------------------------------ kategori
def resolusi_kategori(api: KalodataAPI, alternatif: int = 2, labels=None) -> pd.DataFrame:
    """
    Kata kunci -> ID kategori Kalodata. Nama dari API berbentuk hierarki
    ("Kitchenware-Cookware-Steamers"). Kandidat terbaik = yang memuat kata kunci
    dengan hierarki paling dangkal -> dicentang. Beberapa alternatif ditampilkan
    (tidak dicentang) agar bisa Anda pilih di UI.
    """
    baris = []
    for label, kata_list in config.KATA_CARI_KATEGORI.items():
        if labels is not None and label not in labels:
            continue  # hemat kredit: cari hanya label yang diminta
        for kata in kata_list:
            hasil = api.cari_kategori(kata)
            calon = []
            akar = config.AKAR_KATEGORI.get(label, [])
            for r in hasil:
                cid, nama = r.get("id") or r.get("category_id"), r.get("name") or r.get("category_name") or ""
                if not cid:
                    continue
                if akar and not any(nama == a or nama.startswith(a + "-") for a in akar):
                    continue  # induk salah (mis. Otomotif untuk "cleaning") -> buang
                level = r.get("level") or nama.count("-") + 1
                cocok = all(t in nama.lower() for t in kata.lower().split())
                calon.append((not cocok, int(level), nama, str(cid), cocok))
            calon.sort()
            for i, (_, level, nama, cid, cocok) in enumerate(calon[: 1 + alternatif]):
                # Dicentang hanya bila kata kunci benar-benar cocok; kalau tidak, Anda pilih manual
                baris.append({"label_m1": label, "kata_cari": kata, "category_id": cid, "nama": nama,
                              "level": level, "pakai": i == 0 and cocok and label in config.LABEL_API_UTAMA})
    df = pd.DataFrame(baris)
    return df.drop_duplicates(["label_m1", "category_id"]) if len(df) else df


def simpan_kategori(df: pd.DataFrame, path: Path = FILE_KATEGORI):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(df.to_json(orient="records", force_ascii=False, indent=1), encoding="utf-8")


def baca_kategori(path: Path = FILE_KATEGORI) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))


# ------------------------------------------------------------------ satuan
def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return math.nan


def koreksi_satuan(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Cek kewajaran satuan: omzet ≈ harga × terjual.
    Kalau rasionya ~100, omzet dikirim x100 (sen) dan dibagi 100. Kalau ~0,01, harga yang x100.
    Juga cek harga median masuk akal untuk Rupiah.
    """
    catatan = []
    ok = df[(df["harga"] > 0) & (df["terjual_7h"] > 0) & (df["omzet_7h"] > 0)]
    if len(ok) >= 5:
        rasio = (ok["omzet_7h"] / (ok["harga"] * ok["terjual_7h"])).median()
        if 50 <= rasio <= 200:
            df["omzet_7h"] = df["omzet_7h"] / 100
            catatan.append(f"Omzet tampak dalam satuan x100 (rasio {rasio:.0f}) → dibagi 100.")
        elif 0.005 <= rasio <= 0.02:
            df["harga"] = df["harga"] / 100
            catatan.append(f"Harga tampak dalam satuan x100 (rasio {rasio:.3f}) → dibagi 100.")
        elif not 0.3 <= rasio <= 3:
            catatan.append(f"⚠️ Rasio omzet/(harga×terjual) = {rasio:.2f}, tidak wajar. Cek mata uang/satuan.")
    med = df["harga"].median()
    if pd.notna(med) and med < 1_000:
        catatan.append(f"⚠️ Harga median {med:.2f} terlalu kecil untuk Rupiah. Apakah currency bukan IDR?")
    elif pd.notna(med) and med > 5_000_000:
        df[["harga", "omzet_7h"]] = df[["harga", "omzet_7h"]] / 100
        catatan.append("Harga & omzet tampak x100 → keduanya dibagi 100.")
    return df, catatan


def _rank_ke_df(rows: list[dict], label: str, nama_kat: str) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    out = pd.DataFrame({
        "produk_id": df.get("product_id", pd.Series(dtype=str)).astype(str),
        "nama": df.get("product_name", ""),
        "harga": df.get("unit_price", pd.Series(dtype=float)).map(_num),
        "omzet_7h": df.get("revenue", pd.Series(dtype=float)).map(_num),
        "terjual_7h": df.get("sales_volumn", pd.Series(dtype=float)).map(_num),
        "komisi_raw": df.get("commission_rate", pd.Series(dtype=float)),
        "growth_raw": df.get("revenue_growth_rate", pd.Series(dtype=float)),
        "tanggal_rilis": df.get("launch_date", ""),
    })
    # Kategori asli per produk (level 1/2/3) bila dikirim API; label M1 tetap di depan
    def nama_kat_produk(i):
        bagian = [df.iloc[i].get(k) for k in ("pri_category", "sec_category", "ter_category")
                  if k in df.columns]
        nama = [b.get("category_name", "") for b in bagian if isinstance(b, dict)]
        return " / ".join(n for n in nama if n) or nama_kat
    out["kategori_teks"] = [f"{label} / {nama_kat_produk(i)}" for i in range(len(df))]
    out["kategori_label"] = label
    return out


# ------------------------------------------------------------------ helper detail
_RE_CREATOR = re.compile(r"creator.*(count|num|cnt|total)|(count|num|total).*creator", re.I)


def cari_jumlah_creator(detail: dict):
    """Cari field jumlah creator di respons detail (nama field belum terdokumentasi)."""
    for k, v in detail.items():
        if _RE_CREATOR.search(k) and not isinstance(v, (list, dict)):
            n = _num(v)
            if pd.notna(n):
                return n, k
    return math.nan, None


def cari_shop_id(detail: dict) -> str:
    for k in ("product_shop_id", "shop_id", "seller_id"):
        if detail.get(k):
            return str(detail[k])
    return ""


def hitung_creator_via_rank(api: KalodataAPI, pid: str, batas_atas: float) -> float:
    """Hitung creator dari ranking creator produk. Berhenti begitu melewati batas_atas."""
    total = 0
    for page in (1, 2):
        rows = api.creator_rank_produk(pid, page=page, page_size=100)
        total += len(rows)
        if len(rows) < 100 or total > batas_atas:
            break
    return float(total)


# ------------------------------------------------------------------ alur utama
def tarik_produk(api: KalodataAPI, kategori: pd.DataFrame, f: dict, halaman: int = 1,
                 saring_server: bool = True, max_kandidat: int = 40, ambil_toko: bool = False,
                 progress=None, batas_panggilan: int | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Kembalikan (DataFrame skema internal, catatan). Kategori = baris dengan pakai=True."""
    catatan = []
    say = progress or (lambda *_: None)
    harga = f"{int(f['harga_min'])}-{int(f['harga_max'])}" if saring_server else None
    omzet = f"{int(f['omzet7_min'])}-{int(f['omzet7_max'])}" if saring_server else None

    # 2) ranking per kategori
    bagian = []
    pakai = kategori[kategori["pakai"]] if len(kategori) else kategori
    for i, r in enumerate(pakai.itertuples(), 1):
        say(i / max(len(pakai), 1) * 0.4, f"Ranking {r.label_m1}: {r.nama}")
        for page in range(1, halaman + 1):
            rows = api.product_rank([r.category_id], page=page, harga=harga, omzet=omzet)
            bagian.append(_rank_ke_df(rows, r.label_m1, r.nama))
            if len(rows) < 100:
                break
    df = pd.concat([b for b in bagian if len(b)], ignore_index=True) if any(len(b) for b in bagian) else pd.DataFrame()
    if df.empty:
        return df, ["Ranking kosong. Cek kategori/rentang filter, atau matikan 'saring di server'."]
    df = df.drop_duplicates("produk_id")
    # Pengaman kedua: buang produk yang kategori induknya tidak sesuai label
    induk = df["kategori_teks"].str.split(" / ").str[1].fillna("")
    sah = [not config.AKAR_KATEGORI.get(lbl) or any(i == a or i.startswith(a + "-") for a in config.AKAR_KATEGORI[lbl])
           or i == "" for lbl, i in zip(df["kategori_label"], induk)]
    if not all(sah):
        catatan.append(f"{len(sah) - sum(sah)} produk dibuang: kategori induk tidak sesuai label M1.")
        df = df[sah]
    # Growth bisa >1 walau berbentuk pecahan (1,5 = 150%), jadi skalanya mengikuti KOMISI:
    # kalau komisi dikirim sebagai pecahan (median <= 1), growth juga pecahan -> x100.
    komisi_angka = df["komisi_raw"].map(lambda v: _num(str(v).replace("%", "")))
    # Akun asli (9 Nov 2026) mengirim PERSEN (komisi 6.0 = 6%). Pecahan hanya bila SEMUA <= 1.
    pecahan = bool(komisi_angka.max() <= 1) and not df["komisi_raw"].astype(str).str.contains("%").any()
    df["komisi_pct"] = komisi_angka * (100 if pecahan else 1)
    df["pertumbuhan_pct"] = df["growth_raw"].map(lambda v: _num(str(v).replace("%", ""))) * (100 if pecahan else 1)
    df = df.drop(columns=["komisi_raw", "growth_raw"])
    catatan.append(f"Komisi & growth dibaca sebagai {'pecahan (x100)' if pecahan else 'persen'}.")
    df, c = koreksi_satuan(df)
    catatan += c
    catatan.append(f"{len(df)} produk unik dari {len(pakai)} kategori.")

    # 3) saring lokal dengan field ranking (gratis) sebelum panggilan detail (berbayar)
    pra = (df["harga"].between(f["harga_min"], f["harga_max"])
           & df["omzet_7h"].between(f["omzet7_min"], f["omzet7_max"])
           & (df["pertumbuhan_pct"] >= f["growth_min"]) & (df["komisi_pct"] >= f["komisi_min"]))
    kandidat = df[pra].copy()
    kandidat["_prior"] = kandidat["komisi_pct"].rank(pct=True) + kandidat["pertumbuhan_pct"].rank(pct=True)
    kandidat = kandidat.sort_values("_prior", ascending=False).head(max_kandidat).drop(columns="_prior")
    catatan.append(f"{int(pra.sum())} lolos pra-saring (harga/omzet/growth/komisi); "
                   f"{len(kandidat)} diambil detailnya (maks {max_kandidat}).")

    # 4–5) detail + jumlah creator
    shop_ids, creators, sumber_cre = [], [], set()
    # batas_panggilan: detail berhenti rapi di sini agar sisa anggaran (mis. untuk footage) aman
    for i, pid in enumerate(kandidat["produk_id"], 1):
        if batas_panggilan is not None and api.panggilan >= batas_panggilan:
            catatan.append(f"Detail berhenti di produk ke-{i - 1}: anggaran panggilan tercapai.")
            break
        say(0.4 + i / max(len(kandidat), 1) * 0.45, f"Detail produk {i}/{len(kandidat)}")
        d = api.product_detail(pid)
        shop_ids.append(cari_shop_id(d))
        n, kunci = cari_jumlah_creator(d)
        if pd.isna(n):
            n = hitung_creator_via_rank(api, pid, f["creator_max"])
            sumber_cre.add("ranking creator")
        else:
            sumber_cre.add(f"detail.{kunci}")
        creators.append(n)
    kandidat = kandidat.head(len(creators)).copy()  # buang kandidat yang tidak sempat diambil detailnya
    kandidat["shop_id"] = shop_ids
    kandidat["jumlah_creator"] = creators
    catatan.append("Jumlah creator dari: " + ", ".join(sorted(sumber_cre)))

    # 6) nama toko
    nama_toko = {}
    if ambil_toko:
        unik = [s for s in kandidat["shop_id"].unique() if s]
        for i, sid in enumerate(unik, 1):
            say(0.85 + i / max(len(unik), 1) * 0.15, f"Detail toko {i}/{len(unik)}")
            sd = api.shop_detail(sid)
            nama_toko[sid] = sd.get("shop_name") or sd.get("name") or sid
    # Tanpa detail toko (hemat kredit): toko ditampilkan sebagai ID; nama bisa diambil di Langkah 3
    kandidat["toko"] = kandidat["shop_id"].map(lambda s: nama_toko.get(s, f"shop:{s}" if s else "?"))
    kandidat["url_produk"] = ""  # format link produk dari API belum terverifikasi -> tidak ditebak

    # Produk yang gagal pra-saring tetap disertakan (tanpa detail) agar corong & alasan gagal utuh
    sisa = df[~df["produk_id"].isin(kandidat["produk_id"])].copy()
    sisa["jumlah_creator"] = math.nan
    sisa["toko"] = ""
    sisa["url_produk"] = ""
    hasil = pd.concat([kandidat, sisa], ignore_index=True)
    catatan.append(f"Panggilan API: {api.panggilan} (berbayar), {api.dari_cache} dari cache (gratis).")
    say(1.0, "Selesai")
    return hasil.reset_index(drop=True), catatan


def video_produk(api: KalodataAPI, pid: str, handle_seller: set[str]) -> pd.DataFrame:
    """Daftar video Kalodata untuk satu produk, ditandai seller/affiliate. Bahan Langkah 3."""
    rows = api.video_rank_produk(pid)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    h = df.get("belonged_creator_handle", pd.Series([""] * len(df))).fillna("").astype(str) \
        .str.lstrip("@").str.lower()
    out = pd.DataFrame({
        "handle": h,
        "judul": df.get("video_title", ""),
        "views": df.get("views", pd.Series(dtype=float)).map(_num),
        "omzet": df.get("revenue", pd.Series(dtype=float)).map(_num),
        "video_ai": df.get("ai_video", ""),
        "url": [f"https://www.tiktok.com/@{a}/video/{v}" for a, v in zip(h, df.get("video_id", ""))],
    })
    out = out.drop_duplicates("url")
    out["sumber"] = out["handle"].map(lambda x: "seller" if x in handle_seller else "affiliate_lain")
    return out.sort_values(["sumber", "views"], ascending=[False, False])


FILE_INFO_TOKO = Path(db.DB_PATH).parent / "info_toko.json"


def simpan_info_toko(sd: dict, path: Path = FILE_INFO_TOKO) -> dict:
    """
    Simpan ringkasan detail toko. Field kunci: self_account_revenue = omzet dari akun
    TikTok milik toko sendiri. Rp0 berarti toko TIDAK membuat konten sendiri, sehingga
    hampir pasti tidak ada footage seller (Risiko Hak Footage) -> minta materi via chat toko.
    """
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    nama = sd.get("shop_name") or sd.get("name") or str(sd.get("shop_id"))
    data[nama] = {k: sd.get(k) for k in ("shop_id", "seller_type", "revenue", "self_account_revenue",
                                         "affiliate_revenue", "creator_number", "video_number")}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data[nama]


def baca_info_toko(nama: str, path: Path = FILE_INFO_TOKO) -> dict:
    """Cari info toko berdasarkan nama, atau berdasarkan ID bila nama berbentuk 'shop:<id>'."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if str(nama).startswith("shop:"):
        sid = str(nama).split(":", 1)[1]
        for n, info in data.items():
            if str(info.get("shop_id")) == sid:
                return {**info, "shop_name": n}
        return {}
    return data.get(nama, {})


def nama_toko_dikenal(path: Path = FILE_INFO_TOKO) -> dict:
    """{'shop:<id>': nama} untuk semua toko yang infonya sudah tersimpan."""
    if not path.exists():
        return {}
    return {f"shop:{v.get('shop_id')}": n for n, v in json.loads(path.read_text(encoding="utf-8")).items()}


# Kata umum di nama toko yang tidak boleh dipakai menebak handle.
# Run asli 9 Nov 2026: "SMAEL ID WATCH" sempat menyarankan @sultanwatch21 gara-gara kata "watch".
KATA_UMUM_TOKO = {"official", "store", "shop", "toko", "indonesia", "watch", "watches", "fashion",
                  "home", "beauty", "olshop", "grosir", "murah", "collection", "outfit", "style",
                  "kitchen", "living", "house", "mall", "jaya", "sukses", "makmur"}


def saran_handle_seller(video: pd.DataFrame, nama_toko: str) -> list[str]:
    """Tebak handle seller: handle yang mengandung kata dari nama toko (harus dicek manual)."""
    if video is None or video.empty or not nama_toko:
        return []
    kata = [k for k in re.findall(r"[a-z0-9]+", nama_toko.lower()) if len(k) >= 4
            and k not in KATA_UMUM_TOKO]
    return sorted({h for h in video["handle"] if h and any(k in h.replace(".", "").replace("_", "") for k in kata)})


__all__ = ["KalodataAPI", "KalodataError", "tarik_produk", "resolusi_kategori", "simpan_kategori",
           "baca_kategori", "video_produk", "saran_handle_seller", "koreksi_satuan"]
