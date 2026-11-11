import { asList, kalo } from "@/lib/kalodata";
import { MOCK_CATEGORIES } from "@/lib/mock";
import { bad, fail, isDemo, ok } from "@/lib/respond";
import { REGIONS, REGION_CURRENCY } from "@/lib/types";

export async function GET(req: Request) {
  const sp = new URL(req.url).searchParams;
  const region = (sp.get("region") ?? "ID").toUpperCase();
  const keyword = sp.get("keyword")?.trim().slice(0, 60);
  if (!keyword) return bad("Kata kunci kategori wajib diisi.");
  if (!(REGIONS as readonly string[]).includes(region)) return bad("Negara tidak dikenal.");
  try {
    if (isDemo(sp)) {
      return ok(MOCK_CATEGORIES.filter((c) => c.name.toLowerCase().includes(keyword.toLowerCase())), true, false);
    }
    const { data, cached } = await kalo("/tiktok/category/searchByKeyword", {
      region,
      language: "en-US",
      currency: REGION_CURRENCY[region],
      date_range: "last30Day",
      keyword,
    });
    const rows = asList(data).map((r) => ({ id: String(r.id ?? r.category_id ?? ""), name: String(r.name ?? r.category_name ?? ""), level: r.level }));
    return ok(rows.filter((r) => r.id), false, cached);
  } catch (e) {
    return fail(e);
  }
}
