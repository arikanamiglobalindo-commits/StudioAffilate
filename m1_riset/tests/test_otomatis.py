"""Tes run otomatis (run_otomatis.py) end-to-end terhadap server Kalodata tiruan."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))
import mock_kalodata  # noqa: E402
from m1 import otomatis  # noqa: E402


@pytest.fixture(scope="module")
def server():
    s = mock_kalodata.jalankan()
    yield f"http://127.0.0.1:{s.server_port}/openapi/v1"
    s.shutdown()


def _run(server, tmp_path, *args, key="kunci-tes"):
    env = {**os.environ, "M1_DB": str(tmp_path / "m1.db"), "KALODATA_BASE_URL": server,
           "KALODATA_API_KEY": key}
    p = subprocess.run([sys.executable, str(ROOT / "run_otomatis.py"), *args], env=env,
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout.strip().splitlines()[-1])


def test_run_otomatis(server, tmp_path):
    hasil = _run(server, tmp_path, "--maks-kredit", "4")
    assert hasil["status"] == "ok", hasil
    assert hasil["panggilan_api"] <= 40                       # 4 kredit / 0,1
    siap = [k for k in hasil["kandidat"] if k["status"] == "siap_isi_timestamp"]
    assert 1 <= len(siap) <= otomatis.TOP_N
    for k in siap:
        assert k["video_seller_1"].startswith("https://www.tiktok.com/@tokomaju")
    for k in hasil["kandidat"]:
        if k["omzet_akun_toko"] == 0:
            assert k["status"] == "tanpa_footage_seller"
    assert not any(k["toko"].startswith("shop:") for k in hasil["kandidat"] if k["status"] != "belum_dicek")
    assert "SIAP ISI TIMESTAMP" in hasil["telegram_teks"] and len(hasil["telegram_teks"]) < 4000
    # file untuk Streamlit tersedia
    assert (tmp_path / "hasil_terakhir.pkl").exists() and (tmp_path / "footage_scout.json").exists()
    # run kedua hari yang sama: semua dari cache -> 0 kredit tambahan dari data
    hasil2 = _run(server, tmp_path, "--maks-kredit", "4")
    assert hasil2["status"] == "ok"


def test_kunci_salah_tetap_json(server, tmp_path):
    hasil = _run(server, tmp_path, key="salah")
    assert hasil["status"] == "gagal" and "M1 Riset" in hasil["telegram_teks"]


def test_anggaran():
    r = otomatis.rencana_anggaran(4.0, 6)
    assert r == {"total": 40, "ranking": 6, "detail": 24, "cadangan_footage": 10}


def test_toko_rp0_dilewati_tanpa_panggil_video(tmp_path, monkeypatch):
    """Toko dengan omzet akun sendiri Rp0 tidak boleh memakai kredit untuk daftar video."""
    import pandas as pd
    from m1 import sumber_api

    class Stub:
        panggilan = 0
        video_dipanggil = []

        def shop_detail(self, sid):
            self.panggilan += 1
            return {"shop_id": sid, "shop_name": f"Mawar{sid}",
                    "self_account_revenue": 0.0 if sid == "A" else 1e6}

        def video_rank_produk(self, pid, **kw):
            self.panggilan += 1
            self.video_dipanggil.append(pid)
            return [{"video_id": "1", "belonged_creator_handle": "mawarb.official", "views": 9, "ai_video": 0}]

    f = tmp_path / "info.json"
    monkeypatch.setattr(sumber_api, "FILE_INFO_TOKO", f)
    monkeypatch.setattr(sumber_api.baca_info_toko, "__defaults__", (f,))
    monkeypatch.setattr(sumber_api.simpan_info_toko, "__defaults__", (f,))
    lolos = pd.DataFrame({"produk_id": ["p1", "p2"], "toko": ["shop:A", "shop:B"]})
    api = Stub()
    hasil = otomatis.berburu_footage(api, lolos, 10, {})
    assert api.video_dipanggil == ["p2"]
    assert hasil[0]["status"] == "tanpa_footage_seller" and hasil[1]["status"] == "siap_isi_timestamp"


def test_webhook_dicoba_ulang_lalu_terkirim(server, tmp_path):
    """Varian B (Docker): webhook n8n menerima JSON; gagal pertama dicoba ulang."""
    import http.server
    import threading
    diterima, hitung = [], {"n": 0}

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            hitung["n"] += 1
            body = self.rfile.read(int(self.headers["Content-Length"]))
            if hitung["n"] == 1:          # meniru n8n yang belum siap
                self.send_response(503)
                self.end_headers()
                return
            diterima.append((json.loads(body), self.headers.get("X-M1-Token")))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/webhook/m1-otomatis"
    hasil = _run(server, tmp_path, "--webhook", url, "--jeda-ulang", "0")
    srv.shutdown()
    assert hitung["n"] == 2 and diterima[0][0]["status"] == hasil["status"]
