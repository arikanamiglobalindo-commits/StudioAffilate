// Data DEMO sintetis — dipakai hanya bila pengguna memilih mode demo. Bukan data Kalodata.
const NAMES = [
  "Serum Vitamin C Brightening 30ml", "Hijab Voal Premium Lasercut", "Sandal Slip-On EVA Empuk", "Tumbler Stainless 1L Anti Bocor",
  "Kemeja Linen Oversize Pria", "Sunscreen SPF50 PA++++ Gel", "Rak Bumbu Dapur Putar 2 Tingkat", "Lip Cream Matte Tahan Lama",
  "Celana Kulot Highwaist Wanita", "Earbuds TWS Bluetooth 5.3", "Keripik Pisang Lumer Cokelat", "Mukena Travel Parasut Mini",
  "Body Lotion Niacinamide 250ml", "Tas Selempang Kanvas Unisex", "Lampu Tidur Proyektor Bintang", "Daster Rayon Jumbo Busui",
  "Kopi Gula Aren Sachet isi 20", "Casing HP Magsafe Bening", "Parfum EDP Vanilla Musk 50ml", "Blender Portable USB 380ml",
  "Sepatu Sneakers Putih Kasual", "Masker Rambut Keratin 500g", "Sprei Katun Jepang 160x200", "Mainan Edukasi Balok Kayu",
];

function rng(seed: number) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32);
}

export function mockRank(q: { keyword?: string; page: number; limit: number; sort: string; order: string }) {
  const r = rng(7);
  let rows = NAMES.map((name, i) => {
    const unit_price = Math.round((15 + r() * 250) * 1000);
    const sales = Math.round(200 + r() ** 2 * 40000);
    const revenue = unit_price * sales;
    const video = Math.round(revenue * (0.3 + r() * 0.4));
    const live = Math.round((revenue - video) * r() * 0.8);
    return {
      product_id: (1730000000000000000n + BigInt(i * 7919)).toString(),
      product_name: name,
      launch_date: `2026-${String(1 + Math.floor(r() * 10)).padStart(2, "0")}-${String(1 + Math.floor(r() * 27)).padStart(2, "0")}`,
      revenue: String(revenue),
      sales_volumn: String(sales),
      unit_price: String(unit_price),
      commission_rate: (3 + r() * 17).toFixed(1),
      revenue_growth_rate: (-40 + r() * 220).toFixed(1),
      video_revenue: String(video),
      live_revenue: String(live),
      showcase_revenue: String(revenue - video - live),
    };
  });
  if (q.keyword) rows = rows.filter((x) => x.product_name.toLowerCase().includes(q.keyword!.toLowerCase()));
  const key = q.sort as keyof (typeof rows)[number];
  rows.sort((a, b) => (Number(a[key]) - Number(b[key]) || String(a[key]).localeCompare(String(b[key]))) * (q.order === "ASC" ? 1 : -1));
  return rows.slice((q.page - 1) * q.limit, q.page * q.limit);
}

export function mockDetail(id: string, range: string) {
  const days = range === "last7Day" ? 7 : range === "last90Day" ? 90 : 30;
  const r = rng(Number(id.slice(-6)) || 1);
  const base = 2_000_000 + r() * 30_000_000;
  const slope = -0.5 + r() * 1.5;
  const today = Date.UTC(2026, 10, 10);
  const revenue_trend = Array.from({ length: days }, (_, i) => ({
    date: new Date(today - (days - 1 - i) * 86400000).toISOString().slice(0, 10),
    revenue: Math.round(base * (1 + (slope * i) / days) * (0.75 + r() * 0.5)),
  }));
  return { product_id: id, revenue_trend };
}

export const MOCK_CATEGORIES = [
  { id: "601450", name: "Kecantikan & Perawatan Diri", level: 1 },
  { id: "601152", name: "Pakaian Wanita", level: 1 },
  { id: "600001", name: "Perlengkapan Rumah", level: 1 },
  { id: "700437", name: "Makanan & Minuman", level: 1 },
  { id: "601739", name: "Ponsel & Elektronik", level: 1 },
];
