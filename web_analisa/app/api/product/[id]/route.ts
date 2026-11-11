import { kalo } from "@/lib/kalodata";
import { mockDetail } from "@/lib/mock";
import { toTrend } from "@/lib/normalize";
import { bad, fail, isDemo, ok } from "@/lib/respond";
import { DETAIL_RANGES, REGIONS, REGION_CURRENCY, type ProductDetail } from "@/lib/types";

export async function GET(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const sp = new URL(req.url).searchParams;
  const region = (sp.get("region") ?? "ID").toUpperCase();
  const range = sp.get("range") ?? "last30Day";
  if (!/^\d+$/.test(id)) return bad("ID produk harus angka.");
  if (!(REGIONS as readonly string[]).includes(region)) return bad("Negara tidak dikenal.");
  if (!(DETAIL_RANGES as readonly string[]).includes(range)) return bad("Rentang tanggal tidak valid.");

  try {
    let raw: Record<string, unknown>;
    let cached = false;
    const demo = isDemo(sp);
    if (demo) {
      raw = mockDetail(id, range);
    } else {
      const r = await kalo("/tiktok/product/detail", {
        region,
        language: "en-US",
        currency: REGION_CURRENCY[region],
        date_range: range,
        product_id: id,
        need_extra: true,
      });
      raw = (r.data as Record<string, unknown>) ?? {};
      cached = r.cached;
    }
    const { revenue_trend, product_description: _desc, ...rest } = raw;
    void _desc; // deskripsi panjang tidak dipakai di UI
    return ok<ProductDetail>({ product_id: id, trend: toTrend(revenue_trend), raw: rest }, demo, cached);
  } catch (e) {
    return fail(e);
  }
}
