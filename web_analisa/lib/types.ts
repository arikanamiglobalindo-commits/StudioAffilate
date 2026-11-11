export type Product = {
  product_id: string;
  product_name: string;
  master_image_url?: string;
  launch_date?: string;
  revenue: number | null;
  sales_volume: number | null;
  unit_price: number | null;
  commission_rate: number | null; // rasio, 0.15 = 15%
  revenue_growth_rate: number | null; // rasio, 0.5 = +50%
  live_revenue: number | null;
  video_revenue: number | null;
  showcase_revenue: number | null;
  score?: number; // 0-100, dihitung di aplikasi (bukan dari Kalodata)
};

export type TrendPoint = { label: string; value: number };

export type ProductDetail = {
  product_id: string;
  trend: TrendPoint[];
  raw: Record<string, unknown>;
};

export type ApiErrorKind = "auth" | "quota" | "parameter" | "network" | "upstream";

export type ApiResult<T> =
  | { ok: true; data: T; demo: boolean; cached: boolean }
  | { ok: false; kind: ApiErrorKind; message: string };

export const REGIONS = ["ID", "MY", "TH", "VN", "PH", "SG", "US", "GB", "JP", "MX", "DE", "IT", "FR", "ES", "BR"] as const;

export const REGION_CURRENCY: Record<string, string> = {
  ID: "IDR", MY: "MYR", TH: "THB", VN: "VND", PH: "PHP", SG: "SGD", US: "USD", GB: "GBP",
  JP: "JPY", MX: "MXN", DE: "EUR", IT: "EUR", FR: "EUR", ES: "EUR", BR: "BRL",
};

export const RANK_RANGES = ["lastDay", "last7Day", "last30Day"] as const;
export const DETAIL_RANGES = ["last7Day", "last30Day", "last90Day"] as const;

export const SORT_FIELDS: Record<string, string> = {
  revenue: "Revenue",
  sales_volumn: "Unit terjual",
  revenue_growth_rate: "Pertumbuhan revenue",
  commission_rate: "Komisi",
  unit_price: "Harga",
  video_revenue: "Revenue video",
  launch_date: "Tanggal rilis",
};
