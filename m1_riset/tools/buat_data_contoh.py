"""
buat_data_contoh.py — Membuat file export TIRUAN (dummy) untuk uji coba.

PERINGATAN: angka di sini ACAK, bukan data Kalodata asli. Hanya untuk
mengetes modul sebelum Anda punya export sungguhan. Jangan dipakai riset.

Menghasilkan 2 file di folder sample_data/:
- kalodata_contoh_minggu_lalu.csv  (7 hari sebelumnya, format Indonesia "Rp1,2jt")
- kalodata_contoh_minggu_ini.csv   (format Inggris "Rp1.2M", tanpa kolom growth
                                     di sebagian produk untuk menguji fallback)
Jalankan:  python tools/buat_data_contoh.py
"""
import csv
import random
from pathlib import Path

random.seed(42)
OUT = Path(__file__).resolve().parent.parent / "sample_data"
OUT.mkdir(exist_ok=True)

KAT = [
    ("Womenswear & Underwear", "Muslim Fashion", "Hijab", 12),
    ("Womenswear & Underwear", "Dresses", "Midi Dress", 10),
    ("Menswear & Underwear", "Tops", "Kaos", 9),
    ("Shoes", "Women's Shoes", "Sandal", 9),
    ("Home Supplies", "Home Organizers", "Storage Box", 11),
    ("Home Supplies", "Cleaning Supplies", "Mop", 11),
    ("Kitchenware", "Cookware", "Wajan", 10),
    ("Kitchenware", "Kitchen Utensils", "Spatula", 10),
    ("Beauty & Personal Care", "Skincare", "Serum", 13),
    ("Baby & Maternity", "Feeding", "Botol", 9),
    ("Pet Supplies", "Cat Supplies", "Pasir kucing", 12),
    ("Phones & Electronics", "Accessories", "Charger", 5),
    ("Food & Beverages", "Snacks", "Keripik", 6),
]
NAMA = {"Hijab": "Hijab Pashmina Ceruty Babydoll", "Midi Dress": "Dress Midi Korean Style",
        "Kaos": "Kaos Oversize Cotton Combed 30s", "Sandal": "Sandal Wanita Slip On Empuk",
        "Storage Box": "Kotak Penyimpanan Lipat Organizer Lemari", "Mop": "Alat Pel Spin Mop Lantai",
        "Wajan": "Wajan Anti Lengket Granite 24cm", "Spatula": "Set Spatula Silikon 5 in 1",
        "Serum": "Serum Niacinamide Brightening", "Botol": "Botol Susu Bayi Anti Kolik",
        "Pasir kucing": "Pasir Kucing Gumpal Wangi 10L", "Charger": "Charger Fast 20W",
        "Keripik": "Keripik Pedas Level 5"}


def rp_id(x):  # "Rp15,2jt" / "Rp950rb"
    return f"Rp{x/1e6:.1f}jt".replace(".", ",") if x >= 1e6 else f"Rp{x/1e3:.0f}rb"


def rp_en(x):  # "Rp15.2M" / "Rp950K"
    return f"Rp{x/1e6:.2f}M" if x >= 1e6 else f"Rp{x/1e3:.0f}K"


produk = []
for i in range(320):
    k1, k2, k3, kom = random.choice(KAT)
    pid = str(1729000000000000000 + i * 7919)
    harga = random.choice([random.randint(25, 49), random.randint(50, 500), random.randint(50, 500),
                           random.randint(501, 900)]) * 1000
    omzet_lalu = random.lognormvariate(16.6, 1.1)  # median ~Rp16 jt
    tren = random.choice(["naik", "naik", "naik", "stabil", "puncak", "dikeroyok"])
    if tren == "naik":
        g = random.uniform(0.2, 1.8)
    elif tren == "stabil":
        g = random.uniform(-0.1, 0.19)
    elif tren == "puncak":
        g = random.uniform(-0.4, -0.12)
    else:
        g = random.uniform(0.2, 0.5)
    omzet_ini = omzet_lalu * (1 + g)
    cre_lalu = random.randint(4, 140)
    cre_ini = int(cre_lalu * (random.uniform(1.6, 2.4) if tren == "dikeroyok" else random.uniform(0.9, 1.3)))
    komisi = max(1.0, random.gauss(kom, 2.5))
    produk.append(dict(pid=pid, nama=f"{NAMA[k3]} #{i}", toko=f"Toko{random.randint(1, 60)}",
                       k1=k1, k2=k2, k3=k3, harga=harga, omzet_lalu=omzet_lalu, omzet_ini=omzet_ini,
                       g_lalu=random.uniform(0.1, 0.9) if tren != "puncak" else random.uniform(0.5, 1.5),
                       g=g, cre_lalu=cre_lalu, cre_ini=cre_ini, komisi=komisi))

# Minggu lalu: header Indonesia, format "Rp1,2jt", komisi "12,5%"
with open(OUT / "kalodata_contoh_minggu_lalu.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["ID Produk", "Nama Produk", "Nama Toko", "Kategori Level 1", "Kategori Level 2",
                "Kategori Level 3", "Harga", "Omzet", "Pertumbuhan Omzet", "Jumlah Creator",
                "Komisi", "Link Produk"])
    for p in produk:
        w.writerow([p["pid"], p["nama"], p["toko"], p["k1"], p["k2"], p["k3"], rp_id(p["harga"]),
                    rp_id(p["omzet_lalu"]), f"{p['g_lalu']*100:.1f}%".replace(".", ","), p["cre_lalu"],
                    f"{p['komisi']:.1f}%".replace(".", ","),
                    f"https://shop.tiktok.com/view/product/{p['pid']}"])

# Minggu ini: header Inggris, format "Rp1.2M", growth sebagai pecahan (0.25)
with open(OUT / "kalodata_contoh_minggu_ini.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["Product ID", "Product Name", "Shop Name", "Level 1 Category", "Level 2 Category",
                "Level 3 Category", "Price", "Revenue", "Revenue Growth Rate", "Creators",
                "Commission Rate", "Product Link"])
    for p in produk:
        w.writerow([p["pid"], p["nama"], p["toko"], p["k1"], p["k2"], p["k3"], rp_en(p["harga"]),
                    rp_en(p["omzet_ini"]), f"{p['g']:.3f}", p["cre_ini"], f"{p['komisi']/100:.3f}",
                    f"https://shop.tiktok.com/view/product/{p['pid']}"])

print("Selesai:", *sorted(x.name for x in OUT.glob("*.csv")))
