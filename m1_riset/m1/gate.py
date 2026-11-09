"""
gate.py — GERBANG KEPUTUSAN akhir: Top 5 + alasan lolos/gagal.

Menggabungkan ketiga risiko dalam satu keputusan:
- AKSES DATA  : angka berasal dari export resmi & lolos 6 filter
- TIMING TREN : tidak ada bendera kritis (lewat_puncak, creator_melonjak)
- HAK FOOTAGE : 4 adegan terisi, >= 3 adegan dari seller, timestamp valid

Hanya keputusan "KIRIM" yang boleh masuk antrean n8n.
"""
import pandas as pd

from . import config
from .footage import klip_terpilih, ringkas_kelengkapan, validasi_klip

FLAG_KRITIS = {"lewat_puncak", "creator_melonjak"}
FLAG_PERINGATAN = {"kompetisi_padat", "lonjakan_ekstrem", "belum_ada_riwayat"}


def evaluasi(df_skor: pd.DataFrame, footage: pd.DataFrame, top_n: int = config.TOP_N_GERBANG) -> pd.DataFrame:
    lolos = df_skor[df_skor["lolos"]].sort_values("skor_akhir", ascending=False).head(top_n)
    if lolos.empty:
        return pd.DataFrame()
    ring = ringkas_kelengkapan(footage, lolos["produk_id"]).set_index("produk_id")
    baris = []
    for peringkat, (_, r) in enumerate(lolos.iterrows(), start=1):
        pid = r["produk_id"]
        k = ring.loc[pid]
        ok, gagal, warn = [], [], []

        # 1) Data & filter
        ok.append(f"Lolos 6 filter (skor {r['skor_akhir']:.1f}: komisi {r['komisi_pct']:.1f}%, "
                  f"growth {r['pertumbuhan_pct']:.0f}%, {r['jumlah_creator']:.0f} creator)")

        # 2) Timing tren
        flags = set(r.get("flag_tren") or [])
        kritis = flags & FLAG_KRITIS
        if kritis:
            gagal.append("Timing tren: " + ", ".join(sorted(kritis)))
        else:
            ok.append("Tidak ada tanda lewat puncak / lonjakan creator")
        for f in sorted(flags & FLAG_PERINGATAN):
            warn.append({"belum_ada_riwayat": "Belum ada snapshot minggu lalu — tren belum terverifikasi",
                         "kompetisi_padat": "Creator mendekati batas atas (persaingan padat)",
                         "lonjakan_ekstrem": "Pertumbuhan >300% — cek apakah viral sesaat"}[f])

        # 3) Hak footage
        if k["footage_lengkap_4"]:
            ok.append("Footage 4/4 adegan terisi")
        else:
            kosong = [a for a in config.ADEGAN if k[f"adegan_{a}"] == "KOSONG"]
            gagal.append(f"Footage kurang: adegan {', '.join(kosong)} kosong")
        if k["lolos_syarat_footage"]:
            ok.append(f"Footage seller {int(k['adegan_seller'])}/4 adegan (min {config.MIN_ADEGAN_SELLER})")
        else:
            gagal.append(f"Footage seller hanya {int(k['adegan_seller'])}/4 (wajib >= {config.MIN_ADEGAN_SELLER})")

        klip = klip_terpilih(footage, pid) if len(footage) else []
        for c in klip:
            e = validasi_klip(c["mulai_detik"], c["selesai_detik"])
            if e:
                gagal.append(f"Timestamp adegan {c['adegan']}: {e[0]}")
            if c["berisiko"]:
                warn.append(f"Adegan {c['adegan']} pakai video affiliate lain @{c['creator']} — BERISIKO, "
                            "sumber dicatat")
            elif c["status_hak"] == "seller":
                warn.append(f"Adegan {c['adegan']}: izin seller belum dicatat — minta izin via chat toko")

        baris.append({
            "peringkat": peringkat, "produk_id": pid, "nama": r["nama"], "toko": r["toko"],
            "kategori": r["kategori_m1"], "skor_akhir": r["skor_akhir"],
            "keputusan": "KIRIM" if not gagal else "TAHAN",
            "alasan_lolos": ok, "alasan_gagal": gagal, "peringatan": warn,
            "adegan_seller": int(k["adegan_seller"]), "klip": klip,
        })
    return pd.DataFrame(baris)
