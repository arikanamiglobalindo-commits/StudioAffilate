export const fmtMoney = (v: number | null | undefined, currency: string, compact = true) =>
  v == null
    ? "–"
    : new Intl.NumberFormat("id-ID", { style: "currency", currency, notation: compact ? "compact" : "standard", maximumFractionDigits: compact ? 1 : 0 }).format(v);

export const fmtNum = (v: number | null | undefined) =>
  v == null ? "–" : new Intl.NumberFormat("id-ID", { notation: "compact", maximumFractionDigits: 1 }).format(v);

export const fmtPct = (v: number | null | undefined, signed = false) =>
  v == null ? "–" : new Intl.NumberFormat("id-ID", { style: "percent", maximumFractionDigits: 1, signDisplay: signed ? "exceptZero" : "auto" }).format(v);

export function toCsv(rows: Record<string, unknown>[]): string {
  if (!rows.length) return "";
  const cols = Object.keys(rows[0]);
  const esc = (v: unknown) => {
    let s = v == null ? "" : String(v);
    if (/^[=+\-@\t\r]/.test(s) && typeof v === "string") s = "'" + s; // cegah formula injection di Excel
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [cols.join(","), ...rows.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\n");
}
