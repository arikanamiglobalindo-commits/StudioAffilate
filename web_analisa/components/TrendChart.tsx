"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmtMoney } from "@/lib/format";
import type { TrendPoint } from "@/lib/types";

export const SERIES_COLORS = ["var(--series-1)", "var(--series-2)", "var(--series-3)"];

export type Series = { id: string; name: string; slot: number; trend: TrendPoint[] };

export default function TrendChart({ series, currency }: { series: Series[]; currency: string }) {
  const longest = series.reduce((a, s) => (s.trend.length > a.length ? s.trend : a), [] as TrendPoint[]);
  const data = longest.map((p, i) => {
    const row: Record<string, string | number> = { label: p.label };
    for (const s of series) if (s.trend[i]) row[s.id] = s.trend[i].value;
    return row;
  });
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
        <CartesianGrid stroke="var(--border)" vertical={false} />
        <XAxis dataKey="label" tick={{ fill: "var(--text-muted)", fontSize: 12 }} tickLine={false} axisLine={{ stroke: "var(--border)" }} minTickGap={40} tickFormatter={(v: string) => (/^\d{4}-\d{2}-\d{2}/.test(v) ? v.slice(5, 10) : v)} />
        <YAxis tick={{ fill: "var(--text-muted)", fontSize: 12 }} tickLine={false} axisLine={false} width={88} tickFormatter={(v: number) => fmtMoney(v, currency)} />
        <Tooltip
          cursor={{ stroke: "var(--text-muted)", strokeWidth: 1 }}
          contentStyle={{ background: "var(--surface-1)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 13 }}
          labelStyle={{ color: "var(--text-secondary)" }}
          itemStyle={{ color: "var(--text-primary)" }}
          formatter={(v) => fmtMoney(Number(v), currency, false)}
        />
        {series.length > 1 && <Legend iconType="plainline" formatter={(v) => <span style={{ color: "var(--text-secondary)", fontSize: 13 }}>{v}</span>} />}
        {series.map((s) => (
          <Line key={s.id} type="monotone" dataKey={s.id} name={s.name.length > 32 ? s.name.slice(0, 31) + "…" : s.name} stroke={SERIES_COLORS[s.slot]} strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: "var(--surface-1)", strokeWidth: 2 }} isAnimationActive={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
