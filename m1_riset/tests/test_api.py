"""Tes sumber data Kalodata Open API terhadap server tiruan (tests/mock_kalodata.py)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import mock_kalodata  # noqa: E402
from m1 import config, pipeline, sumber_api  # noqa: E402
from m1.kalodata_api import KalodataAPI, KalodataError  # noqa: E402


@pytest.fixture(scope="module")
def server():
    s = mock_kalodata.jalankan()
    yield f"http://127.0.0.1:{s.server_port}/openapi/v1"
    s.shutdown()


def _api(server, tmp_path, key="kunci-tes", **kw):
    return KalodataAPI(key, base_url=server, cache_dir=tmp_path / "cache", **kw)


def test_kunci_salah(server, tmp_path):
    with pytest.raises(KalodataError) as e:
        _api(server, tmp_path, key="salah").product_rank()
    assert e.value.jenis == "auth"


def test_tarik_produk_lengkap(server, tmp_path):
    api = _api(server, tmp_path, max_panggilan=1000)
    kat = sumber_api.resolusi_kategori(api)
    assert set(kat[kat["pakai"]]["label_m1"]) == config.LABEL_API_UTAMA
    assert "945288" not in set(kat["category_id"])           # kategori otomotif ditolak
    df, catatan = sumber_api.tarik_produk(api, kat, config.DEFAULT_FILTER, max_kandidat=80, ambil_toko=True)
    teks = " ".join(catatan)
    assert "x100" in teks and "dibagi 100" in teks           # omzet x100 terdeteksi
    assert "pecahan" in teks                                  # komisi/growth pecahan
    assert "ranking creator" in teks                          # fallback jumlah creator
    # angka sudah wajar
    k = df[df["jumlah_creator"].notna()]
    assert k["komisi_pct"].between(4, 20).all()
    assert (k["omzet_7h"] / (k["harga"] * k["terjual_7h"])).round(2).eq(1).all()
    assert k["toko"].str.startswith("Toko Maju").all()
    # pipeline jalan & minimal 20 produk lolos
    hasil = pipeline.jalankan(df, "2026-11-09", config.DEFAULT_FILTER, config.KATEGORI_UTAMA,
                              simpan=False, db_path=tmp_path / "t.db")
    lolos = hasil[hasil["lolos"]]
    assert len(lolos) >= config.TARGET_PRODUK_LOLOS
    assert set(lolos["kategori_m1"]) <= {"Fashion", "Rumah Tangga"}


def test_cache_hemat_kredit(server, tmp_path):
    a1 = _api(server, tmp_path)
    a1.product_rank(["601"])
    a2 = _api(server, tmp_path)
    a2.product_rank(["601"])
    assert a1.panggilan == 1 and a2.panggilan == 0 and a2.dari_cache == 1


def test_batas_panggilan(server, tmp_path):
    api = _api(server, tmp_path, max_panggilan=2)
    api.product_rank(["601"])
    api.product_rank(["602"])
    with pytest.raises(KalodataError) as e:
        api.product_rank(["603"])
    assert e.value.jenis == "batas_run"


def test_video_dan_saran_seller(server, tmp_path):
    api = _api(server, tmp_path)
    v = sumber_api.video_produk(api, "1760100003", {"tokomaju3"})
    assert set(v["sumber"]) == {"seller", "affiliate_lain"}
    assert v.iloc[0]["url"].startswith("https://www.tiktok.com/@tokomaju3/video/")
    assert sumber_api.saran_handle_seller(v, "Toko Maju S3") == ["tokomaju3"]


def test_kategori_kata_utuh():
    import pandas as pd
    from m1.filters import tentukan_kategori
    df = pd.DataFrame({"kategori_teks": ["Pet Supplies / Perlengkapan Hewan", "Home Organizers"],
                       "nama": ["Pasir kucing", "Kotak"]})
    hasil = tentukan_kategori(df, config.KATEGORI_UTAMA).tolist()
    assert hasil == ["", "Rumah Tangga"]   # "pel"/"lap" tidak lagi cocok dengan "Perlengkapan"


def test_format_persen_akun_asli():
    """Bentuk baris seperti respons asli 9 Nov 2026: komisi & growth dalam PERSEN, kategori bertingkat."""
    import pandas as pd
    rows = [{"product_id": str(i), "product_name": f"P{i}", "revenue": 18_606_790.58, "commission_rate": k,
             "revenue_growth_rate": g, "sales_volumn": 90, "unit_price": 206_742.12,
             "pri_category": {"category_id": "600024", "category_name": "Kitchenware"},
             "ter_category": {"category_id": "600032", "category_name": "Vacuum Flasks"}}
            for i, (k, g) in enumerate([(6.0, 8856.06), (0.0, 105.43), (12.0, 25.0), (7.0, 0.5), (9.0, 40.0)])]
    df = sumber_api._rank_ke_df(rows, "Rumah Tangga - dapur", "Kitchenware")
    assert df["kategori_teks"].iloc[0] == "Rumah Tangga - dapur / Kitchenware / Vacuum Flasks"
    komisi = df["komisi_raw"].map(sumber_api._num)
    assert not (komisi.max() <= 1)  # -> dibaca persen, tidak dikali 100
