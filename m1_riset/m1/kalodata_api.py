"""
kalodata_api.py — Klien Kalodata Open API resmi.

Risiko: AKSES DATA.

KEPUTUSAN TEKNIS:
- Memakai Open API RESMI (kunci dari kalodata.com/open-center/account), bukan
  scraping. Jadi sesuai ToS dan akun tidak berisiko diblokir.
- Bentuk request diambil dari klien open-source yang memakai API ini
  (github.com/sailtonight/kalodata-skill): semua POST JSON ke
  https://www.kalodata.com/openapi/v1, kunci di header "secret-key",
  respons {"success", "code", "message", "data"}.
  Ini BUKAN dokumentasi resmi. Tombol "Tes API" di UI mengecek ulang dengan
  akun Anda sebelum dipakai.
- API memakai KREDIT. Untuk menjaga budget:
    1) setiap respons di-cache ke disk per hari, sehingga run ulang di hari yang
       sama tidak memakai kredit lagi;
    2) batas jumlah panggilan per run (max_panggilan);
    3) saldo kredit dicek sebelum dan sesudah run.
"""
import hashlib
import json
import time
from datetime import date
from pathlib import Path

import requests

BASE_URL = "https://www.kalodata.com/openapi/v1"


class KalodataError(Exception):
    """Error yang sudah diterjemahkan ke bahasa yang bisa ditindaklanjuti."""

    def __init__(self, pesan: str, jenis: str = "umum"):
        super().__init__(pesan)
        self.jenis = jenis  # auth | kuota | parameter | jaringan | batas_run | umum


class KalodataAPI:
    def __init__(self, api_key: str, base_url: str = BASE_URL, region: str = "ID",
                 language: str = "en-US", currency: str = "IDR", max_panggilan: int = 200,
                 cache_dir: Path | str | None = None, timeout: float = 30.0):
        if not api_key:
            raise KalodataError("API key Kalodata belum diisi (KALODATA_API_KEY di file .env).", "auth")
        self.key = api_key
        self.base = base_url.rstrip("/")
        self.region, self.language, self.currency = region, language, currency
        self.max_panggilan = max_panggilan
        self.timeout = timeout
        self.panggilan = 0          # panggilan nyata ke server (memakai kredit)
        self.dari_cache = 0         # panggilan yang dijawab cache (gratis)
        self.log: list[str] = []
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ inti HTTP
    def _cache_path(self, path: str, body: dict) -> Path | None:
        if not self.cache_dir:
            return None
        kunci = json.dumps({"p": path, "b": body, "d": date.today().isoformat()}, sort_keys=True)
        return self.cache_dir / (hashlib.sha1(kunci.encode()).hexdigest() + ".json")

    def _req(self, path: str, body: dict | None = None, method: str = "POST", pakai_cache: bool = True):
        body = body or {}
        cp = self._cache_path(path, body) if pakai_cache else None
        if cp and cp.exists():
            self.dari_cache += 1
            return json.loads(cp.read_text(encoding="utf-8"))
        gratis = path.startswith("/credit/")  # cek saldo/log tidak memakai kredit
        if not gratis and self.panggilan >= self.max_panggilan:
            raise KalodataError(f"Batas {self.max_panggilan} panggilan per run tercapai "
                                "(pengaman kredit). Naikkan batas di UI bila memang perlu.", "batas_run")
        headers = {"Content-Type": "application/json;charset=UTF-8", "secret-key": self.key}
        url = self.base + path
        terakhir = ""
        for coba in range(3):
            try:
                if method == "GET":
                    r = requests.get(url, params=body, headers=headers, timeout=self.timeout)
                else:
                    r = requests.post(url, json=body, headers=headers, timeout=self.timeout)
                if not gratis:
                    self.panggilan += 1
                if r.status_code >= 500:
                    terakhir = f"HTTP {r.status_code}"
                    time.sleep(1 + coba)
                    continue
                if r.status_code in (401, 403):
                    raise KalodataError("API key ditolak Kalodata (401/403). Cek kunci di Open Center.", "auth")
                env = r.json()
            except requests.RequestException as e:
                terakhir = e.__class__.__name__
                time.sleep(1 + coba)
                continue
            except ValueError:
                terakhir = "respons bukan JSON"
                time.sleep(1 + coba)
                continue
            if env.get("success"):
                data = env.get("data")
                if cp:
                    cp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                self.log.append(f"OK {path}")
                return data
            return self._gagal(env, path)
        raise KalodataError(f"Kalodata tidak bisa dihubungi setelah 3 percobaan ({terakhir}).", "jaringan")

    def _gagal(self, env: dict, path: str):
        kode, pesan = str(env.get("code")), str(env.get("message") or "")
        low = pesan.lower()
        self.log.append(f"GAGAL {path}: {kode} {pesan}")
        if "not found" in low or "未找到" in pesan:
            return []  # hasil kosong yang sah
        if kode == "501" and low.startswith("the key"):
            raise KalodataError(f"API key ditolak: {pesan}", "auth")
        if kode == "2016":
            if any(k in low for k in ("must be", "invalid", "required", "parameter")):
                raise KalodataError(f"Parameter ditolak Kalodata: {pesan}", "parameter")
            raise KalodataError(f"Batas paket/kredit: {pesan}. Cek saldo di Open Center.", "kuota")
        raise KalodataError(f"Error Kalodata ({kode}): {pesan or 'tidak diketahui'}")

    @staticmethod
    def _list(data) -> list:
        """Respons ranking bisa berupa list atau {"data": [...]}."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return data["data"]
        return []

    def _dasar(self, date_range: str = "last7Day") -> dict:
        return {"region": self.region, "language": self.language,
                "currency": self.currency, "date_range": date_range}

    # ------------------------------------------------------------ endpoint
    def saldo(self) -> dict:
        """Sisa kredit. Tidak di-cache (harus selalu angka terbaru)."""
        return self._req("/credit/balance", {}, method="GET", pakai_cache=False) or {}

    def cari_kategori(self, kata: str) -> list[dict]:
        body = {**self._dasar("last30Day"), "keyword": kata}
        return self._list(self._req("/tiktok/category/searchByKeyword", body))

    def product_rank(self, category_ids: list | None = None, page: int = 1, page_size: int = 100,
                     sort: str = "revenue_growth_rate", harga: str | None = None,
                     omzet: str | None = None, date_range: str = "last7Day",
                     hanya_affiliate: bool = True) -> list[dict]:
        """Ranking produk. Halaman 1–5, isi 5–100 per halaman (batas API)."""
        body = {**self._dasar(date_range), "page_number": max(1, min(5, page)),
                "page_size": max(5, min(100, page_size)),
                "sort_field": {"field": sort, "type": "DESC"}}
        if category_ids:
            body["category_ids"] = [str(c) for c in category_ids]
        if harga:
            body["unit_price_range"] = harga      # "50000-500000"
        if omzet:
            body["revenue_range"] = omzet         # "15000000-200000000"
        if hanya_affiliate:
            body["is_affiliate"] = 1              # hanya produk yang membuka komisi affiliate
        return self._list(self._req("/tiktok/product/rank", body))

    def product_detail(self, product_id: str, date_range: str = "last7Day") -> dict:
        body = {**self._dasar(date_range), "product_id": str(product_id), "need_extra": True}
        d = self._req("/tiktok/product/detail", body)
        return d if isinstance(d, dict) else {}

    def shop_detail(self, shop_id: str, date_range: str = "last7Day") -> dict:
        body = {**self._dasar(date_range), "shop_id": str(shop_id), "need_extra": True}
        d = self._req("/tiktok/shop/detail", body)
        return d if isinstance(d, dict) else {}

    def creator_rank_produk(self, product_id: str, page: int = 1, page_size: int = 100,
                            date_range: str = "last7Day") -> list[dict]:
        body = {**self._dasar(date_range), "product_id": str(product_id), "page_number": page,
                "page_size": page_size, "sort_field": {"field": "revenue", "type": "DESC"}}
        return self._list(self._req("/tiktok/creator/rank", body))

    def video_rank_produk(self, product_id: str, page_size: int = 50,
                          date_range: str = "last30Day") -> list[dict]:
        """Video yang menjual produk ini, termasuk handle pembuatnya (untuk cek seller vs affiliate)."""
        body = {**self._dasar(date_range), "product_id": str(product_id), "need_extra": True,
                "page_number": 1, "page_size": page_size,
                "sort_field": {"field": "views", "type": "DESC"}}
        return self._list(self._req("/tiktok/video/rank", body))
