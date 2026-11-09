"""
config.py — Semua angka & aturan yang DIKUNCI sejak awal (blueprint 12 minggu).

Kenapa satu file? Supaya filter, kategori, bobot skor, dan definisi adegan
hanya diubah di satu tempat. UI Streamlit membaca nilai default dari sini,
jadi kalau Anda "menyimpang" dari blueprint, itu terlihat jelas di UI.
"""

# ---------------------------------------------------------------------------
# 1) Enam filter tab Produk (nilai default = kriteria blueprint)
#    Risiko yang ditangani: Timing Tren (pertumbuhan, jumlah creator)
# ---------------------------------------------------------------------------
DEFAULT_FILTER = {
    "harga_min": 50_000,          # Rp
    "harga_max": 500_000,         # Rp
    "omzet7_min": 15_000_000,     # Rp, omzet 7 hari
    "omzet7_max": 200_000_000,    # Rp — di atas ini biasanya sudah dikeroyok creator besar
    "growth_min": 20.0,           # % pertumbuhan omzet
    "creator_min": 10,            # <10 creator = belum terbukti laku lewat affiliate
    "creator_max": 150,           # >150 creator = persaingan sudah padat
    "komisi_min": 8.0,            # % komisi
}

# ---------------------------------------------------------------------------
# 2) Kategori. Pencocokan memakai kata kunci pada teks kategori Kalodata
#    (level 1/2/3 digabung) + nama produk, karena nama kategori Kalodata bisa
#    berbahasa Inggris atau Indonesia tergantung pengaturan akun.
# ---------------------------------------------------------------------------
KATEGORI_UTAMA = {
    "Fashion": [
        "fashion", "pakaian", "busana", "womenswear", "menswear", "muslim",
        "hijab", "kerudung", "gamis", "kaos", "kemeja", "celana", "rok", "dress",
        "sepatu", "shoes", "sandal", "tas", "bags", "luggage", "aksesoris fashion",
        "fashion accessories", "jaket", "outer", "underwear", "pakaian dalam",
    ],
    # Rumah Tangga SENGAJA dibatasi ke 3 sub-niche blueprint: dapur, organizer, kebersihan
    "Rumah Tangga": [
        # dapur
        "dapur", "kitchen", "kitchenware", "masak", "cookware", "peralatan makan",
        "tableware", "pisau", "wajan", "panci", "spatula", "talenan",
        # organizer
        "organizer", "penyimpanan", "storage", "rak", "kotak penyimpanan",
        "gantungan", "hanger", "laci", "container", "toples",
        # kebersihan
        "kebersihan", "cleaning", "pembersih", "sapu", "pel", "mop", "lap",
        "sikat", "brush", "tempat sampah", "laundry", "deterjen",
    ],
}

# Kategori tambahan: HANYA boleh diaktifkan bila rata-rata komisi di data
# Kalodata yang diimpor >= AMBANG_KOMISI_TAMBAHAN. UI mengunci checkbox-nya.
KATEGORI_OPSIONAL = {
    "Kecantikan & Perawatan": [
        "beauty", "kecantikan", "perawatan", "personal care", "skincare",
        "makeup", "kosmetik", "serum", "sunscreen", "parfum", "rambut",
    ],
    "Ibu & Bayi": [
        "baby", "bayi", "maternity", "ibu", "anak", "mpasi", "popok", "kids",
    ],
    "Perlengkapan Hewan": [
        "pet", "hewan", "kucing", "anjing", "cat ", "dog", "aquarium",
    ],
}
AMBANG_KOMISI_TAMBAHAN = 10.0  # %

# ---------------------------------------------------------------------------
# 3) Skor (0–100). Pakai SKALA ABSOLUT, bukan relatif terhadap batch.
#    Alasan: skor minggu 3 dan minggu 7 bisa dibandingkan langsung.
# ---------------------------------------------------------------------------
BOBOT_SKOR = {"komisi": 0.35, "pertumbuhan": 0.35, "kepadatan": 0.30}

SKALA_SKOR = {
    # komisi 8% -> 0 poin, 25% -> 100 poin
    "komisi": (8.0, 25.0),
    # pertumbuhan 20% -> 0, 200% -> 100 (dibatasi; >200% sering lonjakan sesaat)
    "pertumbuhan": (20.0, 200.0),
    # kepadatan = omzet 7 hari per creator (Rp). Rp100 rb/creator -> 0, Rp5 jt -> 100
    # Makin besar = permintaan belum terbagi ke banyak creator.
    "kepadatan": (100_000.0, 5_000_000.0),
}

# Penalti Timing Tren (dikurangkan dari skor akhir)
PENALTI_TREN = {
    "lewat_puncak": 15,
    "creator_melonjak": 15,
    "kompetisi_padat": 8,
    "lonjakan_ekstrem": 5,
}

# ---------------------------------------------------------------------------
# 4) Pemetaan adegan VEO3 (dikunci). Persona AI hanya untuk hook & CTA;
#    4 adegan isi WAJIB footage produk asli.
# ---------------------------------------------------------------------------
ADEGAN = {
    "masalah": "Masalah — kondisi sebelum pakai produk (berantakan, kotor, ribet, tidak pas)",
    "demo": "Demo pemakaian — tangan/orang memakai produk, gerakan jelas",
    "hasil": "Hasil — kondisi sesudah (rapi, bersih, outfit jadi, before-after)",
    "detail": "Detail / isi paket — close-up bahan, ukuran, unboxing, isi box",
}
DURASI_ADEGAN_MIN = 1.0   # detik
DURASI_ADEGAN_MAX = 15.0  # detik — klip pendek mengurangi risiko dianggap re-upload utuh

# Status hak footage, dari paling aman ke paling berisiko
STATUS_HAK = {
    "seller_izin": "Seller resmi + izin tercatat (AMAN)",
    "seller": "Seller resmi, izin belum tercatat (cukup aman, minta izin)",
    "affiliate_berisiko": "Video affiliate lain (CADANGAN, BERISIKO)",
}
STATUS_SELLER = {"seller_izin", "seller"}
MIN_ADEGAN_SELLER = 3  # Gerbang: minimal 3 dari 4 adegan dari seller

# ---------------------------------------------------------------------------
# 5) Alias kolom export Kalodata -> nama kolom internal.
#    Header export bisa berubah (bahasa/versi), jadi dicocokkan secara longgar.
#    Kalau tetap tidak cocok, UI menyediakan pemetaan manual.
# ---------------------------------------------------------------------------
ALIAS_KOLOM = {
    "produk_id": ["product id", "id produk", "produk id", "item id", "product_id"],
    "nama": ["product name", "nama produk", "product", "produk", "title", "judul", "name"],
    "toko": ["shop", "shop name", "nama toko", "toko", "store", "seller", "penjual"],
    "kategori": ["category", "kategori", "product category", "kategori produk",
                 "level 1 category", "kategori level 1"],
    "kategori2": ["level 2 category", "kategori level 2", "sub category", "subkategori"],
    "kategori3": ["level 3 category", "kategori level 3"],
    "harga": ["price", "harga", "avg price", "average price", "harga rata rata",
              "unit price", "harga satuan"],
    "omzet_7h": ["revenue", "omzet", "pendapatan", "gmv", "revenue 7d", "omzet 7 hari",
                 "revenue last 7 days", "total revenue", "penjualan rp"],
    "omzet_sebelumnya": ["previous revenue", "omzet sebelumnya", "revenue previous period",
                         "last period revenue"],
    "pertumbuhan_pct": ["revenue growth", "growth rate", "pertumbuhan", "revenue growth rate",
                        "pertumbuhan omzet", "growth", "tingkat pertumbuhan"],
    "jumlah_creator": ["creators", "creator", "jumlah creator", "affiliate creators",
                       "kreator", "jumlah kreator", "creator count", "related creators"],
    "komisi_pct": ["commission rate", "komisi", "commission", "tingkat komisi",
                   "persentase komisi"],
    "terjual_7h": ["sales", "item sold", "terjual", "units sold", "penjualan", "volume"],
    "jumlah_video": ["videos", "video", "jumlah video", "related videos", "video count"],
    "url_produk": ["product link", "product url", "link produk", "url", "link", "tiktok link"],
    "tanggal_rilis": ["launch date", "tanggal rilis", "listing date", "tanggal listing"],
}
KOLOM_WAJIB = ["nama", "harga", "omzet_7h", "jumlah_creator", "komisi_pct", "kategori"]

# ---------------------------------------------------------------------------
# 6) Kalodata Open API — kata kunci untuk mencari ID kategori (sekali saja).
#    Label diawali nama kategori M1 agar langsung terpetakan ke filter kategori.
# ---------------------------------------------------------------------------
KATA_CARI_KATEGORI = {
    # 1 kata kunci = 1 panggilan (0,1 kredit), cukup SEKALI lalu disimpan.
    # Hasil Kalodata berbentuk hierarki "Induk-Anak-Cucu"; dipilih yang paling dangkal.
    "Fashion": ["womenswear", "menswear", "muslim fashion", "shoes", "fashion accessories"],
    "Rumah Tangga - dapur": ["kitchenware"],
    "Rumah Tangga - organizer": ["home organizers"],
    "Rumah Tangga - kebersihan": ["home care supplies"],
    "Kecantikan & Perawatan": ["beauty"],
    "Ibu & Bayi": ["baby"],
    "Perlengkapan Hewan": ["pet supplies"],
}
# Pengaman: kategori hasil pencarian HARUS berinduk salah satu nama ini.
# (Run 9 Nov 2026: kata "cleaning" sempat memilih "Automotive & Motorcycle-Car Washing".)
AKAR_KATEGORI = {
    "Fashion": ["Womenswear & Underwear", "Menswear & Underwear", "Muslim Fashion", "Shoes",
                "Fashion Accessories", "Luggage & Bags"],
    "Rumah Tangga - dapur": ["Kitchenware"],
    "Rumah Tangga - organizer": ["Home Supplies"],
    "Rumah Tangga - kebersihan": ["Home Supplies", "Household Appliances"],
    "Kecantikan & Perawatan": ["Beauty & Personal Care"],
    "Ibu & Bayi": ["Baby & Maternity"],
    "Perlengkapan Hewan": ["Pet Supplies"],
}
LABEL_API_UTAMA = {"Fashion", "Rumah Tangga - dapur", "Rumah Tangga - organizer",
                   "Rumah Tangga - kebersihan"}
# Diukur dari akun Anda (9 Nov 2026): SETIAP panggilan data = 0,10 kredit; cek saldo gratis.
BIAYA_PER_PANGGILAN = 0.10
API_DEFAULT = {
    "halaman": 1,          # 1 halaman = 100 produk per kategori = 0,1 kredit
    "max_kandidat": 40,    # produk yang diambil detailnya (0,1 kredit/produk) per run
    "max_panggilan": 80,   # pengaman kredit per run (80 x 0,1 = 8 kredit)
}

# Target hasil per run (kriteria "selesai")
TARGET_PRODUK_LOLOS = 20
TOP_N_GERBANG = 5
