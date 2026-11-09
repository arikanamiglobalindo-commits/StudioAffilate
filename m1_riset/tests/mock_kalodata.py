"""
mock_kalodata.py — Server tiruan Kalodata Open API untuk tes (DATA ACAK, bukan asli).

Sengaja meniru "kejutan" yang mungkin terjadi di API asli:
- omzet dikirim x100 (harus terdeteksi & dikoreksi)
- komisi & growth berupa pecahan (0.12 = 12%, 1.5 = 150%)
- detail produk TIDAK punya jumlah creator (harus fallback ke ranking creator)
Jalankan manual:  python tests/mock_kalodata.py 5680
"""
import http.server
import json
import random
import sys
import threading

KATEGORI = {"womenswear": ("601", "Womenswear & Underwear", 1), "menswear": ("602", "Menswear", 1),
            "muslim fashion": ("603", "Muslim Fashion", 1), "shoes": ("604", "Shoes", 1),
            "fashion accessories": ("605", "Fashion Accessories", 1), "kitchenware": ("701", "Kitchenware", 1),
            "cookware": ("702", "Cookware", 2), "home organizers": ("711", "Home Supplies-Home Organizers", 2),
            "storage": ("712", "Storage & Organisation", 3), "cleaning supplies": ("721", "Cleaning Supplies", 2),
            "household cleaning": ("722", "Household Cleaning", 3), "beauty": ("801", "Beauty & Personal Care", 1),
            "skincare": ("802", "Skincare", 2), "baby & maternity": ("901", "Baby & Maternity", 1),
            "home care supplies": ("721", "Home Supplies-Home Care Supplies", 2), "beauty": ("801", "Beauty & Personal Care", 1),
            "baby": ("901", "Baby & Maternity", 1),
            "pet supplies": ("951", "Pet Supplies", 1)}


def _produk(cid: str, n=100):
    rnd = random.Random(int(cid))
    out = []
    for i in range(n):
        harga = rnd.choice([rnd.randint(30, 49), rnd.randint(50, 500), rnd.randint(50, 500)]) * 1000
        terjual = rnd.randint(40, 900)
        omzet = harga * terjual
        out.append({"product_id": f"17{cid}{i:05d}", "product_name": f"Produk {cid}-{i}",
                    "unit_price": harga, "sales_volumn": terjual, "revenue": omzet * 100,  # x100!
                    "commission_rate": round(rnd.uniform(0.04, 0.2), 3),
                    "revenue_growth_rate": round(rnd.uniform(-0.3, 2.5), 3), "launch_date": "2026-08-01"})
    return out


class Handler(http.server.BaseHTTPRequestHandler):
    calls = []

    def _send(self, data, ok=True):
        body = json.dumps({"success": ok, "code": 0 if ok else 2016, "message": "" if ok else "x",
                           "data": data}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        Handler.calls.append(self.path)
        if self.headers.get("secret-key") != "kunci-tes":
            return self._auth()
        self._send({"totalRemain": 1000, "mainRemain": 1000})

    def _auth(self):
        body = json.dumps({"success": False, "code": 501, "message": "The key is not allowed"}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = self.path.split("/openapi/v1")[-1]
        Handler.calls.append(path)
        if self.headers.get("secret-key") != "kunci-tes":
            return self._auth()
        b = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if path == "/tiktok/category/searchByKeyword":
            cid, nama, lvl = KATEGORI.get(b["keyword"], ("999", "Lain", 1))
            jebakan = [{"id": 945288, "name": "Automotive & Motorcycle-Car Washing & Maintenance-Cleaning & Care Fluids"}]
            return self._send(jebakan + [{"id": cid, "name": nama}])
        if path == "/tiktok/product/rank":
            cid = (b.get("category_ids") or ["500"])[0]
            rows = _produk(cid)
            if b.get("unit_price_range"):  # server menyaring harga (satuan rupiah)
                lo, hi = map(float, b["unit_price_range"].split("-"))
                rows = [r for r in rows if lo <= r["unit_price"] <= hi]
            return self._send(rows[: b.get("page_size", 20)] if b.get("page_number", 1) == 1 else [])
        if path == "/tiktok/product/detail":
            pid = b["product_id"]
            d = {"product_id": pid, "product_shop_id": f"S{int(pid[-2:]) % 15}"}
            if int(pid) % 2 == 0:  # sebagian produk membawa creator_number seperti API asli
                d["creator_number"] = random.Random(int(pid)).randint(3, 180)
            return self._send(d)
        if path == "/tiktok/creator/rank":
            n = random.Random(int(b["product_id"])).randint(3, 180)
            sisa = max(0, n - (b["page_number"] - 1) * 100)
            return self._send([{"creator_id": f"c{i}", "creator_handle": f"cr{i}"} for i in range(min(100, sisa))])
        if path == "/tiktok/shop/detail":
            n = int(b["shop_id"].lstrip("S") or 0)
            # toko bernomor kelipatan 3 tidak punya konten sendiri (omzet akun sendiri 0)
            return self._send({"shop_id": b["shop_id"], "shop_name": f"Toko Maju {b['shop_id']}",
                               "self_account_revenue": 0.0 if n % 3 == 0 else 5_000_000.0})
        if path == "/tiktok/video/rank":
            sid = int(b["product_id"][-2:]) % 15
            return self._send([{"video_id": f"73{i}", "belonged_creator_handle": h, "video_title": "demo",
                                "views": 1000 * (5 - i), "revenue": 10, "ai_video": 0}
                               for i, h in enumerate([f"tokomaju{sid}", f"tokomaju{sid}", "creator_a", "creator_b"])])
        return self._send(None, ok=False)

    def log_message(self, *a):
        pass


def jalankan(port=0):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


if __name__ == "__main__":
    s = jalankan(int(sys.argv[1]) if len(sys.argv) > 1 else 5680)
    print(f"Mock Kalodata di http://127.0.0.1:{s.server_port}/openapi/v1")
    threading.Event().wait()
