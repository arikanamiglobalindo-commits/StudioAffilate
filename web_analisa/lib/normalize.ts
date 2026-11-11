import type { Product, TrendPoint } from "./types";

/** Kalodata kadang mengirim angka sebagai string ("1,234.5", "12%"). */
export function num(v: unknown): number | null {
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v !== "string" || !v.trim()) return null;
  const n = Number(v.replace(/[,%\s]/g, ""));
  return Number.isFinite(n) ? n : null;
}

/** Kalodata mengirim persen sebagai angka persen (7 = 7%, 96.93 = +96,93%); diubah ke rasio. */
export function ratio(v: unknown): number | null {
  const n = num(v);
  return n === null ? null : n / 100;
}

export function toProduct(r: Record<string, unknown>): Product {
  return {
    product_id: String(r.product_id ?? ""),
    product_name: String(r.product_name ?? "(tanpa nama)"),
    master_image_url: typeof r.master_image_url === "string" ? r.master_image_url : undefined,
    launch_date: r.launch_date == null ? undefined : String(r.launch_date),
    revenue: num(r.revenue),
    sales_volume: num(r.sales_volumn ?? r.sales_volume), // "sales_volumn" adalah ejaan asli API
    unit_price: num(r.unit_price),
    commission_rate: ratio(r.commission_rate),
    revenue_growth_rate: ratio(r.revenue_growth_rate),
    live_revenue: num(r.live_revenue),
    video_revenue: num(r.video_revenue),
    showcase_revenue: num(r.showcase_revenue),
  };
}

const SCORE_WEIGHTS = { revenue: 0.35, revenue_growth_rate: 0.3, sales_volume: 0.2, commission_rate: 0.15 } as const;

/**
 * Skor potensi 0-100 = rata-rata tertimbang peringkat persentil produk di dalam
 * hasil yang sedang tampil (revenue 35%, pertumbuhan 30%, unit 20%, komisi 15%).
 * Ini skor relatif buatan aplikasi, bukan metrik Kalodata.
 */
export function withScores(products: Product[]): Product[] {
  const pct = (key: keyof typeof SCORE_WEIGHTS) => {
    const vals = products.map((p) => p[key]).filter((v): v is number => v !== null).sort((a, b) => a - b);
    return (v: number | null) => {
      if (v === null || vals.length < 2) return null;
      const below = vals.filter((x) => x < v).length;
      return below / (vals.length - 1);
    };
  };
  const fns = Object.fromEntries((Object.keys(SCORE_WEIGHTS) as (keyof typeof SCORE_WEIGHTS)[]).map((k) => [k, pct(k)]));
  return products.map((p) => {
    let sum = 0;
    let w = 0;
    for (const k of Object.keys(SCORE_WEIGHTS) as (keyof typeof SCORE_WEIGHTS)[]) {
      const s = fns[k](p[k]);
      if (s !== null) {
        sum += Math.min(1, s) * SCORE_WEIGHTS[k];
        w += SCORE_WEIGHTS[k];
      }
    }
    return { ...p, score: w ? Math.round((sum / w) * 100) : undefined };
  });
}

/**
 * revenue_trend = revenue harian dalam mata uang yang diminta (jumlahnya sama dengan
 * revenue periode). Item berupa angka polos tanpa tanggal, atau objek {tanggal, nilai}.
 * Tanpa tanggal, titik diberi label relatif: "H-1" = hari terakhir dalam periode.
 */
export function toTrend(raw: unknown): TrendPoint[] {
  if (!Array.isArray(raw)) return [];
  const n = raw.length;
  return raw.flatMap((item, i): TrendPoint[] => {
    if (item && typeof item === "object") {
      const o = item as Record<string, unknown>;
      const labelKey = Object.keys(o).find((k) => /date|day|time/i.test(k));
      const valueKey = Object.keys(o).find((k) => k !== labelKey && num(o[k]) !== null);
      const v = valueKey ? num(o[valueKey]) : null;
      if (v === null) return [];
      return [{ label: labelKey ? String(o[labelKey]) : `H-${n - i}`, value: v }];
    }
    const v = num(item);
    return v === null ? [] : [{ label: `H-${n - i}`, value: v }];
  });
}
