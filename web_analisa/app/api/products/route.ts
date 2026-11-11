import { asList, kalo } from "@/lib/kalodata";
import { mockRank } from "@/lib/mock";
import { toProduct, withScores } from "@/lib/normalize";
import { bad, fail, isDemo, ok } from "@/lib/respond";
import { RANK_RANGES, REGIONS, REGION_CURRENCY, SORT_FIELDS } from "@/lib/types";

const MINMAX = /^\d+(\.\d+)?-\d+(\.\d+)?$/;

export async function GET(req: Request) {
  const sp = new URL(req.url).searchParams;
  const region = (sp.get("region") ?? "ID").toUpperCase();
  const range = sp.get("range") ?? "last7Day";
  const sort = sp.get("sort") ?? "revenue";
  const order = sp.get("order") === "ASC" ? "ASC" : "DESC";
  const page = Math.min(5, Math.max(1, Number(sp.get("page")) || 1));
  const limit = Math.min(100, Math.max(5, Number(sp.get("limit")) || 20));
  const keyword = sp.get("keyword")?.trim().slice(0, 100) || undefined;
  const category = sp.get("category")?.trim();
  const price = sp.get("price")?.trim();
  const revenue = sp.get("revenue")?.trim();

  if (!(REGIONS as readonly string[]).includes(region)) return bad("Negara tidak dikenal.");
  if (!(RANK_RANGES as readonly string[]).includes(range)) return bad("Rentang tanggal tidak valid.");
  if (!(sort in SORT_FIELDS)) return bad("Kolom urutan tidak valid.");
  if (price && !MINMAX.test(price)) return bad('Rentang harga harus berformat "min-max".');
  if (revenue && !MINMAX.test(revenue)) return bad('Rentang revenue harus berformat "min-max".');
  if (category && !/^\d+$/.test(category)) return bad("ID kategori harus angka.");

  try {
    if (isDemo(sp)) {
      const rows = mockRank({ keyword, page, limit, sort, order });
      return ok({ products: withScores(rows.map(toProduct)), currency: "IDR" }, true, false);
    }
    const currency = REGION_CURRENCY[region];
    const body: Record<string, unknown> = {
      region,
      language: "en-US",
      currency,
      date_range: range,
      page_number: page,
      page_size: limit,
      sort_field: { field: sort, type: order },
      need_image: 1,
    };
    if (keyword) body.keyword = keyword;
    if (category) body.category_ids = [category];
    if (price) body.unit_price_range = price;
    if (revenue) body.revenue_range = revenue;
    const { data, cached } = await kalo("/tiktok/product/rank", body);
    const products = asList(data).map(toProduct).filter((p) => p.product_id);
    return ok({ products: withScores(products), currency }, false, cached);
  } catch (e) {
    return fail(e);
  }
}
