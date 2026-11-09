"""
Tes otomatis M1. Jalankan:  python -m pytest -q
Memakai data contoh dummy (tools/buat_data_contoh.py) dan database sementara.
"""
import http.server
import json
import subprocess
import sys
import threading
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from m1 import config, db, gate, importer, n8n_client, pipeline  # noqa: E402
from m1.footage import tentukan_status_hak, validasi_klip, handle_dari_url  # noqa: E402
from m1.parsing import parse_angka, persen_ke_angka, parse_timestamp  # noqa: E402


@pytest.fixture(scope="module")
def data_contoh():
    subprocess.run([sys.executable, str(ROOT / "tools" / "buat_data_contoh.py")], check=True)
    return ROOT / "sample_data"


@pytest.fixture()
def dbp(tmp_path):
    return tmp_path / "tes.db"


def _impor(path):
    raw = importer.baca_file(open(path, "rb"), path.name)
    df, _ = importer.normalisasi(raw, importer.tebak_pemetaan(raw.columns))
    return df


# ---------------- parsing (Risiko: Akses Data) ----------------
@pytest.mark.parametrize("teks,mode,harap", [
    ("Rp1,23jt", "id", 1_230_000), ("Rp 950rb", "id", 950_000), ("Rp15.2M", "en", 15_200_000),
    ("Rp1,2M", "id", 1_200_000_000), ("Rp 1.234.567", "en", 1_234_567),
    ("Rp50.000 - Rp75.000", "en", 62_500), ("Rp3.170M", "en", 3_170_000),
])
def test_parse_rupiah(teks, mode, harap):
    assert parse_angka(teks, mode) == pytest.approx(harap)


def test_persen_pecahan_dan_teks():
    assert persen_ke_angka(pd.Series(["0.25", "1.414"])).tolist() == pytest.approx([25.0, 141.4])
    assert persen_ke_angka(pd.Series(["12,5%", "+20%"])).tolist() == pytest.approx([12.5, 20.0])


def test_timestamp():
    assert parse_timestamp("1:02.5") == 62.5 and parse_timestamp("7") == 7.0


# ---------------- pipeline (Risiko: Timing Tren) ----------------
def test_dua_minggu_minimal_20_lolos(data_contoh, dbp):
    pipeline.jalankan(_impor(data_contoh / "kalodata_contoh_minggu_lalu.csv"), "2026-11-01",
                      config.DEFAULT_FILTER, config.KATEGORI_UTAMA, db_path=dbp)
    hasil = pipeline.jalankan(_impor(data_contoh / "kalodata_contoh_minggu_ini.csv"), "2026-11-08",
                              config.DEFAULT_FILTER, config.KATEGORI_UTAMA, db_path=dbp)
    lolos = hasil[hasil["lolos"]]
    assert len(lolos) >= config.TARGET_PRODUK_LOLOS
    # Semua produk lolos benar-benar memenuhi 6 filter
    f = config.DEFAULT_FILTER
    assert lolos["harga"].between(f["harga_min"], f["harga_max"]).all()
    assert lolos["omzet_7h"].between(f["omzet7_min"], f["omzet7_max"]).all()
    assert (lolos["pertumbuhan_pct"] >= f["growth_min"]).all()
    assert lolos["jumlah_creator"].between(f["creator_min"], f["creator_max"]).all()
    assert (lolos["komisi_pct"] >= f["komisi_min"]).all()
    assert set(lolos["kategori_m1"]) <= set(config.KATEGORI_UTAMA)
    # Snapshot minggu lalu terpakai -> bendera tren muncul
    semua_flag = set(hasil["flag_tren"].explode().dropna())
    assert {"lewat_puncak", "creator_melonjak"} & semua_flag
    assert "belum_ada_riwayat" not in set(lolos["flag_tren"].explode().dropna())


# ---------------- footage (Risiko: Hak Footage) ----------------
def test_status_hak():
    s = {"tokoa.official"}
    assert tentukan_status_hak("TokoA.Official", s, "chat 3 Nov") == "seller_izin"
    assert tentukan_status_hak("tokoa.official", s) == "seller"
    assert tentukan_status_hak("creatorlain", s) == "affiliate_berisiko"
    assert tentukan_status_hak("", s) == "affiliate_berisiko"
    assert handle_dari_url("https://www.tiktok.com/@Toko.A/video/123") == "toko.a"


def test_validasi_klip():
    assert validasi_klip(3, 8) == []
    assert validasi_klip(8, 3)
    assert validasi_klip(0, 40)  # terlalu panjang


def _isi_footage(pid, statuses, dbp):
    for adg, st in zip(config.ADEGAN, statuses):
        if st:
            db.tambah_footage({"produk_id": pid, "adegan": adg, "url": f"https://www.tiktok.com/@x/video/{adg}",
                               "mulai": 1.0, "selesai": 5.0, "creator_handle": "x", "status_hak": st,
                               "bukti_izin": "", "catatan": ""}, dbp)


def test_gerbang(data_contoh, dbp):
    hasil = pipeline.jalankan(_impor(data_contoh / "kalodata_contoh_minggu_ini.csv"), "2026-11-08",
                              config.DEFAULT_FILTER, config.KATEGORI_UTAMA, simpan=False, db_path=dbp)
    top = hasil[hasil["lolos"]].sort_values("skor_akhir", ascending=False).head(5)
    pids = top["produk_id"].tolist()
    _isi_footage(pids[0], ["seller", "seller_izin", "seller", "affiliate_berisiko"], dbp)  # 3 seller -> KIRIM
    _isi_footage(pids[1], ["seller", "seller", "affiliate_berisiko", "affiliate_berisiko"], dbp)  # 2 -> TAHAN
    _isi_footage(pids[2], ["seller", "seller", "seller", None], dbp)  # adegan kurang -> TAHAN
    ev = gate.evaluasi(hasil, db.baca_footage(path=dbp)).set_index("produk_id")
    assert len(ev) == 5
    kritis = bool(set(top.iloc[0]["flag_tren"]) & gate.FLAG_KRITIS)
    assert ev.loc[pids[0], "keputusan"] == ("TAHAN" if kritis else "KIRIM")
    assert ev.loc[pids[1], "keputusan"] == "TAHAN"
    assert ev.loc[pids[2], "keputusan"] == "TAHAN"
    assert ev.loc[pids[3], "keputusan"] == "TAHAN"  # tanpa footage


# ---------------- n8n (kirim + anti ganda) ----------------
class _Penangkap(http.server.BaseHTTPRequestHandler):
    diterima = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Penangkap.diterima.append(body)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *a):
        pass


def test_kirim_n8n_tanpa_ganda(data_contoh, dbp):
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Penangkap)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/webhook/m1-antrean"
    hasil = pipeline.jalankan(_impor(data_contoh / "kalodata_contoh_minggu_ini.csv"), "2026-11-08",
                              config.DEFAULT_FILTER, config.KATEGORI_UTAMA, simpan=False, db_path=dbp)
    prod = hasil[hasil["lolos"]].iloc[0].to_dict()
    baris = {"adegan_seller": 3, "klip": [{"adegan": "masalah", "url": "u", "mulai_detik": 1.0,
                                           "selesai_detik": 4.0, "creator": "x", "status_hak": "seller",
                                           "bukti_izin": "", "berisiko": False}]}
    p = n8n_client.buat_payload(baris, prod, "2026-11-08")
    json.dumps(p)  # harus bisa jadi JSON
    assert n8n_client.kirim([p], url, db_path=dbp)[0]["ok"]
    assert "dilewati" in n8n_client.kirim([p], url, db_path=dbp)[0]["pesan"]
    assert len(_Penangkap.diterima) == 1 and _Penangkap.diterima[0]["masalah_url"] == "u"
    srv.shutdown()
