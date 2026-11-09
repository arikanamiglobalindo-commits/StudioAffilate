"""
otomatis.py — Satu run M1 tanpa campur tangan: dijalankan n8n (Senin & Kamis).

Alur:
  1. Cek saldo kredit (gratis). Berhenti kalau saldo kurang dari batas minimum.
  2. Bagi anggaran kredit: ranking -> detail produk -> cadangan "berburu footage".
  3. Tarik data + 6 filter + skor + snapshot (memakai modul yang sama dengan Streamlit).
  4. Berburu footage seller: telusuri produk lolos dari skor tertinggi.
     - Info toko diambil sekali saja lalu disimpan (data/info_toko.json).
     - Toko dengan omzet akun sendiri = Rp0 DILEWATI tanpa memanggil daftar video
       (hampir pasti tidak ada footage seller -> hemat kredit).
     - Daftar video dicek; handle yang mirip nama toko = "saran seller".
     Berhenti setelah TOP_N produk yang punya footage seller, atau cadangan habis.
  5. Hasil disimpan untuk Streamlit (hasil_terakhir.pkl + footage_scout.json) dan
     dikembalikan sebagai dict JSON untuk n8n (Data Table + Telegram).

Yang SENGAJA tidak otomatis (Risiko Hak Footage):
  - handle saran TIDAK disimpan sebagai seller resmi -> Anda konfirmasi di Langkah 3
  - timestamp adegan -> manual
  - pengiriman ke antrean VEO3 -> tetap lewat Gerbang di Streamlit
"""
import json
import math
from datetime import date
from pathlib import Path

import pandas as pd

from . import config, db, pipeline, sumber_api
from .footage import daftar_handle
from .kalodata_api import KalodataAPI, KalodataError

FILE_SCOUT = Path(db.DB_PATH).parent / "footage_scout.json"
FILE_HASIL = Path(db.DB_PATH).parent / "hasil_terakhir.pkl"
SALDO_MINIMUM = 1.0      # di bawah ini run dibatalkan
CADANGAN_FOOTAGE = 10    # panggilan untuk info toko + daftar video
TOP_N = config.TOP_N_GERBANG


def _angka(x, nd=1):
    try:
        f = float(x)
        return None if math.isnan(f) else round(f, nd)
    except (TypeError, ValueError):
        return None


def rencana_anggaran(maks_kredit: float, n_kategori: int, halaman: int = 1) -> dict:
    """Bagi anggaran panggilan: ranking dulu, cadangan footage, sisanya untuk detail."""
    total = int(maks_kredit / config.BIAYA_PER_PANGGILAN + 1e-9)
    ranking = n_kategori * halaman
    cadangan = min(CADANGAN_FOOTAGE, max(0, total - ranking) // 3)
    detail = max(0, total - ranking - cadangan)
    return {"total": total, "ranking": ranking, "detail": detail, "cadangan_footage": cadangan}


def berburu_footage(api: KalodataAPI, lolos: pd.DataFrame, batas_panggilan: int,
                    seller_terverifikasi: dict) -> list[dict]:
    """Telusuri produk lolos (urut skor) sampai TOP_N punya footage seller atau kuota habis."""
    hasil, ditemukan = [], 0
    awal = api.panggilan
    for r in lolos.itertuples():
        sisa = batas_panggilan - (api.panggilan - awal)
        rec = {"produk_id": r.produk_id, "status": "belum_dicek", "saran_handle_seller": [],
               "omzet_akun_toko": None, "video_seller": [], "jumlah_video": 0}
        if ditemukan >= TOP_N or sisa <= 0:
            hasil.append(rec)
            continue
        toko = r.toko
        # 1) info toko (sekali saja per toko, lalu dari file -> tidak bayar dua kali)
        info = sumber_api.baca_info_toko(toko)
        if info.get("shop_name"):
            toko = info["shop_name"]
        if not info and str(toko).startswith("shop:"):
            try:
                sd = api.shop_detail(toko.split(":", 1)[1])
                if sd.get("shop_name"):
                    info = sumber_api.simpan_info_toko(sd)
                    toko = sd["shop_name"]
                    lolos.loc[lolos["toko"] == r.toko, "toko"] = toko
            except KalodataError:
                pass
        rec["toko"] = toko
        rec["omzet_akun_toko"] = _angka((info or {}).get("self_account_revenue"), 0)
        if rec["omzet_akun_toko"] == 0:
            rec["status"] = "tanpa_footage_seller"
            rec["alasan"] = "omzet akun milik toko Rp0 (toko tidak membuat konten sendiri)"
            hasil.append(rec)
            continue
        if batas_panggilan - (api.panggilan - awal) <= 0:
            hasil.append(rec)
            continue
        # 2) daftar video produk
        try:
            terverif = daftar_handle(seller_terverifikasi.get(toko, ""))
            v = sumber_api.video_produk(api, r.produk_id, terverif)
        except KalodataError as e:
            rec["alasan"] = str(e)
            hasil.append(rec)
            continue
        saran = sorted(terverif) or sumber_api.saran_handle_seller(v, toko)
        rec["saran_handle_seller"] = saran
        rec["handle_terverifikasi"] = bool(terverif)
        rec["jumlah_video"] = int(len(v))
        if len(v):
            vs = v[v["handle"].isin(saran) & ~v["video_ai"].astype(str).isin(["1", "True", "true"])]
            rec["video_seller"] = vs[["handle", "url", "views"]].head(5).to_dict("records")
        if rec["video_seller"]:
            rec["status"] = "siap_isi_timestamp"
            ditemukan += 1
        else:
            rec["status"] = "tanpa_footage_seller"
            rec["alasan"] = "tidak ada video dari akun yang mirip nama toko"
        hasil.append(rec)
    return hasil


def teks_telegram(ringkas: dict) -> str:
    """Pesan teks polos (tanpa Markdown agar tidak gagal di-parse Telegram), < 4000 karakter."""
    b = [f"M1 Riset {ringkas['tanggal']} - {ringkas['status'].upper()}"]
    if ringkas["status"] != "ok":
        b.append(ringkas.get("pesan", ""))
        return "\n".join(b)
    b.append(f"Lolos filter: {ringkas['jumlah_lolos']} (target {config.TARGET_PRODUK_LOLOS}) dari "
             f"{ringkas['jumlah_impor']} produk")
    b.append(f"Kredit: {ringkas['kredit_terpakai']} terpakai, sisa {ringkas['kredit_akhir']}")
    siap = [k for k in ringkas["kandidat"] if k["status"] == "siap_isi_timestamp"]
    b.append(f"\nSIAP ISI TIMESTAMP ({len(siap)}):")
    for k in siap:
        b.append(f"#{k['peringkat']} {k['nama'][:60]}\n  skor {k['skor_akhir']} | komisi {k['komisi_pct']}% | "
                 f"{int(k['jumlah_creator'] or 0)} creator\n  seller? @{', @'.join(k['saran_handle_seller'])}"
                 f"{' (terverifikasi)' if k.get('handle_terverifikasi') else ' (CEK MANUAL)'}\n  {k['video_seller_1']}")
    lewat = [k for k in ringkas["kandidat"] if k["status"] == "tanpa_footage_seller"][:5]
    if lewat:
        b.append("\nDILEWATI (tanpa footage seller):")
        b += [f"#{k['peringkat']} {k['nama'][:45]} - {k.get('alasan', '')[:60]}" for k in lewat]
    b.append("\nTUGAS ANDA: buka Streamlit > Langkah 3: konfirmasi handle seller, isi timestamp 4 adegan, "
             "lalu Langkah 4 Gerbang.")
    if ringkas["peringatan"]:
        b.append("\nPERINGATAN: " + " | ".join(ringkas["peringatan"]))
    return "\n".join(b)[:3900]


def jalankan(api: KalodataAPI, maks_kredit: float = 4.0, tanggal: str | None = None) -> dict:
    tanggal = tanggal or date.today().isoformat()
    ringkas = {"tanggal": tanggal, "status": "ok", "peringatan": [], "kandidat": []}
    try:
        saldo_awal = float(api.saldo().get("totalRemain", 0))
    except KalodataError as e:
        ringkas.update(status="gagal", pesan=f"Tidak bisa cek saldo: {e}")
        ringkas["telegram_teks"] = teks_telegram(ringkas)
        return ringkas
    ringkas["kredit_awal"] = saldo_awal
    if saldo_awal < SALDO_MINIMUM:
        ringkas.update(status="gagal", pesan=f"Saldo kredit {saldo_awal} < {SALDO_MINIMUM}. Isi ulang di Open Center.")
        ringkas["telegram_teks"] = teks_telegram(ringkas)
        return ringkas
    maks = min(maks_kredit, saldo_awal - 0.2)
    if maks < maks_kredit:
        ringkas["peringatan"].append(f"anggaran diturunkan ke {maks:.1f} kredit karena saldo")

    kat = sumber_api.baca_kategori()
    if kat.empty:
        kat = sumber_api.resolusi_kategori(api, labels=config.LABEL_API_UTAMA)
        sumber_api.simpan_kategori(kat)
    n_kat = int(kat["pakai"].sum())
    sudah = api.panggilan  # panggilan pencarian kategori (bila ada) ikut dihitung dalam anggaran
    rencana = rencana_anggaran(maks - sudah * config.BIAYA_PER_PANGGILAN, n_kat)
    api.max_panggilan = sudah + rencana["total"]
    ringkas["rencana_panggilan"] = rencana

    try:
        df, catatan = sumber_api.tarik_produk(
            api, kat, config.DEFAULT_FILTER, max_kandidat=rencana["detail"],
            batas_panggilan=sudah + rencana["ranking"] + rencana["detail"])
    except KalodataError as e:
        ringkas.update(status="gagal", pesan=f"Tarik data gagal: {e}")
        ringkas["telegram_teks"] = teks_telegram(ringkas)
        return ringkas
    ringkas["catatan"] = catatan
    if df.empty:
        ringkas.update(status="gagal", pesan="Ranking kosong: " + " ".join(catatan))
        ringkas["telegram_teks"] = teks_telegram(ringkas)
        return ringkas

    hasil = pipeline.jalankan(df, tanggal, config.DEFAULT_FILTER, config.KATEGORI_UTAMA)
    hasil.attrs["tanggal_data"] = tanggal
    lolos = hasil[hasil["lolos"]].sort_values("skor_akhir", ascending=False).copy()
    ringkas["jumlah_impor"], ringkas["jumlah_lolos"] = int(len(hasil)), int(len(lolos))
    if len(lolos) < config.TARGET_PRODUK_LOLOS:
        ringkas["peringatan"].append(f"hanya {len(lolos)} lolos (<{config.TARGET_PRODUK_LOLOS}); "
                                     "naikkan maks kredit bila sering terjadi")

    sisa = api.max_panggilan - api.panggilan
    scout = berburu_footage(api, lolos, sisa, db.peta_handle_seller())
    # nama toko yang sudah diketahui (run ini atau sebelumnya) -> ganti semua 'shop:<id>'
    hasil["toko"] = hasil["toko"].map(lambda t: sumber_api.nama_toko_dikenal().get(t, t))
    hasil.to_pickle(FILE_HASIL)
    simpan_scout(scout, tanggal)

    peta = {s["produk_id"]: s for s in scout}
    for i, r in enumerate(hasil[hasil["lolos"]].sort_values("skor_akhir", ascending=False).itertuples(), 1):
        s = peta.get(r.produk_id, {})
        vs = s.get("video_seller") or []
        ringkas["kandidat"].append({
            "kunci": f"{r.produk_id}_{tanggal}", "peringkat": i, "produk_id": str(r.produk_id),
            "nama": r.nama, "toko": r.toko, "kategori": r.kategori_m1,
            "harga": _angka(r.harga, 0), "omzet_7h": _angka(r.omzet_7h, 0),
            "pertumbuhan_pct": _angka(r.pertumbuhan_pct), "jumlah_creator": _angka(r.jumlah_creator, 0),
            "komisi_pct": _angka(r.komisi_pct), "skor_akhir": _angka(r.skor_akhir),
            "flag_tren": ",".join(r.flag_tren or []),
            "status": s.get("status", "belum_dicek"), "alasan": s.get("alasan", ""),
            "omzet_akun_toko": s.get("omzet_akun_toko"),
            "saran_handle_seller": s.get("saran_handle_seller", []),
            "handle_terverifikasi": s.get("handle_terverifikasi", False),
            "jumlah_video_seller": len(vs), "video_seller_1": vs[0]["url"] if vs else "",
            "tanggal": tanggal,
        })
    try:
        saldo_akhir = float(api.saldo().get("totalRemain", 0))
    except KalodataError:
        saldo_akhir = None
    ringkas["kredit_akhir"] = saldo_akhir
    ringkas["kredit_terpakai"] = round(saldo_awal - saldo_akhir, 2) if saldo_akhir is not None else None
    ringkas["panggilan_api"] = api.panggilan
    ringkas["telegram_teks"] = teks_telegram(ringkas)
    return ringkas


def simpan_scout(scout: list[dict], tanggal: str, path: Path = FILE_SCOUT):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"tanggal": tanggal, "produk": {s["produk_id"]: s for s in scout}},
                               ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def baca_scout(path: Path = FILE_SCOUT) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("produk", {})
