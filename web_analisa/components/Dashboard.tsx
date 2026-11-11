"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fmtMoney, fmtNum, fmtPct, toCsv } from "@/lib/format";
import { DETAIL_RANGES, RANK_RANGES, REGIONS, SORT_FIELDS, type ApiResult, type Product, type ProductDetail } from "@/lib/types";
import TrendChart, { SERIES_COLORS, type Series } from "./TrendChart";

const RANGE_LABEL: Record<string, string> = { lastDay: "Kemarin", last7Day: "7 hari", last30Day: "30 hari", last90Day: "90 hari" };
const MAX_COMPARE = 3;

type Filters = { region: string; range: string; keyword: string; category: string; categoryName: string; priceMin: string; priceMax: string; sort: string; order: "DESC" | "ASC"; page: number };
type Picked = { product: Product; slot: number };
type Cat = { id: string; name: string };

async function getJson<T>(url: string, signal?: AbortSignal): Promise<ApiResult<T>> {
  try {
    const res = await fetch(url, { signal });
    return (await res.json()) as ApiResult<T>;
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    return { ok: false, kind: "network", message: "Tidak bisa menghubungi server aplikasi." };
  }
}

const input = "h-9 rounded-md border border-line bg-surface px-2.5 text-sm text-ink outline-none focus:border-accent";
const btn = "h-9 rounded-md border border-line bg-surface px-3 text-sm text-ink hover:bg-page disabled:opacity-40";

export default function Dashboard() {
  const [f, setF] = useState<Filters>({ region: "ID", range: "last7Day", keyword: "", category: "", categoryName: "", priceMin: "", priceMax: "", sort: "revenue", order: "DESC", page: 1 });
  const [keywordDraft, setKeywordDraft] = useState("");
  const [demo, setDemo] = useState(false);
  const [state, setState] = useState<{ loading: boolean; error?: { kind: string; message: string }; products: Product[]; currency: string; cached: boolean }>({ loading: true, products: [], currency: "IDR", cached: false });
  const [picked, setPicked] = useState<Picked[]>([]);
  const [trendRange, setTrendRange] = useState<string>("last30Day");
  const [details, setDetails] = useState<Record<string, { loading: boolean; error?: string; trend?: ProductDetail["trend"] }>>({});
  const [credit, setCredit] = useState<string | null>(null);
  const [catQuery, setCatQuery] = useState("");
  const [cats, setCats] = useState<Cat[] | null>(null);
  const [catMsg, setCatMsg] = useState("");

  const set = (patch: Partial<Filters>) => setF((p) => ({ ...p, page: 1, ...patch }));

  // Debounce kata kunci supaya tidak memanggil API di setiap ketikan (hemat kuota).
  useEffect(() => {
    const t = setTimeout(() => setF((p) => (p.keyword === keywordDraft.trim() ? p : { ...p, keyword: keywordDraft.trim(), page: 1 })), 500);
    return () => clearTimeout(t);
  }, [keywordDraft]);

  const priceOk = (f.priceMin === "") === (f.priceMax === "");
  const query = useMemo(() => {
    const sp = new URLSearchParams({ region: f.region, range: f.range, sort: f.sort, order: f.order, page: String(f.page), limit: "20" });
    if (f.keyword) sp.set("keyword", f.keyword);
    if (f.category) sp.set("category", f.category);
    if (f.priceMin !== "" && f.priceMax !== "") sp.set("price", `${f.priceMin}-${f.priceMax}`);
    if (demo) sp.set("demo", "1");
    return sp.toString();
  }, [f, demo]);

  useEffect(() => {
    if (!priceOk) return;
    const ac = new AbortController();
    setState((s) => ({ ...s, loading: true }));
    getJson<{ products: Product[]; currency: string }>(`/api/products?${query}`, ac.signal)
      .then((r) => {
        if (r.ok) setState({ loading: false, products: r.data.products, currency: r.data.currency, cached: r.cached });
        else setState((s) => ({ ...s, loading: false, error: { kind: r.kind, message: r.message }, products: [] }));
      })
      .catch(() => {});
    return () => ac.abort();
  }, [query, priceOk]);

  useEffect(() => {
    if (demo) return;
    getJson<{ total: unknown }>("/api/credit").then((r) => setCredit(r.ok && r.data.total != null ? String(r.data.total) : null)).catch(() => {});
  }, [demo]);

  // Detail (tren) hanya diambil untuk produk yang dipilih pengguna.
  const fetched = useRef(new Set<string>());
  useEffect(() => {
    for (const { product } of picked) {
      const key = `${product.product_id}|${f.region}|${trendRange}|${demo}`;
      if (fetched.current.has(key)) continue;
      fetched.current.add(key);
      setDetails((d) => ({ ...d, [key]: { loading: true } }));
      getJson<ProductDetail>(`/api/product/${product.product_id}?region=${f.region}&range=${trendRange}${demo ? "&demo=1" : ""}`).then((r) => {
        if (!r.ok) fetched.current.delete(key);
        setDetails((d) => ({ ...d, [key]: r.ok ? { loading: false, trend: r.data.trend } : { loading: false, error: r.message } }));
      });
    }
  }, [picked, f.region, trendRange, demo]);

  const toggle = (p: Product) =>
    setPicked((cur) => {
      if (cur.some((x) => x.product.product_id === p.product_id)) return cur.filter((x) => x.product.product_id !== p.product_id);
      if (cur.length >= MAX_COMPARE) return cur;
      // Warna mengikuti produk: ambil slot kosong pertama, slot produk lain tidak berubah.
      const slot = [0, 1, 2].find((s) => !cur.some((x) => x.slot === s))!;
      return [...cur, { product: p, slot }];
    });

  const searchCats = useCallback(async () => {
    if (!catQuery.trim()) return;
    setCatMsg("Mencari…");
    const r = await getJson<Cat[]>(`/api/categories?region=${f.region}&keyword=${encodeURIComponent(catQuery.trim())}${demo ? "&demo=1" : ""}`);
    if (r.ok) {
      setCats(r.data);
      setCatMsg(r.data.length ? "" : "Kategori tidak ditemukan.");
    } else setCatMsg(r.message);
  }, [catQuery, f.region, demo]);

  const exportCsv = () => {
    const rows = state.products.map((p, i) => ({
      peringkat: (f.page - 1) * 20 + i + 1, product_id: p.product_id, nama: p.product_name, skor_potensi: p.score ?? "",
      revenue: p.revenue ?? "", unit_terjual: p.sales_volume ?? "", harga: p.unit_price ?? "", komisi: p.commission_rate ?? "",
      pertumbuhan_revenue: p.revenue_growth_rate ?? "", revenue_video: p.video_revenue ?? "", revenue_live: p.live_revenue ?? "",
      tanggal_rilis: p.launch_date ?? "", mata_uang: state.currency, negara: f.region, periode: f.range, sumber: demo ? "DEMO (bukan data asli)" : "Kalodata",
    }));
    const url = URL.createObjectURL(new Blob(["﻿" + toCsv(rows)], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `produk-${f.region}-${f.range}${demo ? "-DEMO" : ""}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const series: Series[] = picked.flatMap(({ product, slot }) => {
    const d = details[`${product.product_id}|${f.region}|${trendRange}|${demo}`];
    return d?.trend?.length ? [{ id: product.product_id, name: product.product_name, slot, trend: d.trend }] : [];
  });
  const detailOf = (p: Product) => details[`${p.product_id}|${f.region}|${trendRange}|${demo}`];
  const cur = state.currency;

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <header className="mb-4 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Analisa Produk TikTok Shop</h1>
          <p className="text-sm text-ink2">Sumber data: Kalodata Open API{state.cached && !demo ? " · dari cache" : ""}</p>
        </div>
        <div className="text-sm text-ink2">{credit != null && !demo ? <>Sisa kredit API: <b className="num text-ink">{credit}</b></> : null}</div>
      </header>

      {demo && (
        <div role="status" className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <span><b>⚠ MODE DEMO</b> — semua angka di bawah adalah data contoh buatan, bukan data Kalodata.</span>
          <button className="underline" onClick={() => { setDemo(false); setPicked([]); }}>Kembali ke data asli</button>
        </div>
      )}

      {/* Filter: satu baris di atas tabel dan grafik */}
      <section className="mb-4 flex flex-wrap items-end gap-3 rounded-lg border border-line bg-surface p-3">
        <label className="flex flex-col gap-1 text-xs text-ink2">Kata kunci
          <input className={`${input} w-56`} placeholder="mis. serum, hijab…" value={keywordDraft} onChange={(e) => setKeywordDraft(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-xs text-ink2">Negara
          <select className={input} value={f.region} onChange={(e) => { set({ region: e.target.value, category: "", categoryName: "" }); setPicked([]); setCats(null); }}>
            {REGIONS.map((r) => <option key={r}>{r}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-ink2">Periode
          <select className={input} value={f.range} onChange={(e) => set({ range: e.target.value })}>
            {RANK_RANGES.map((r) => <option key={r} value={r}>{RANGE_LABEL[r]}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-ink2">Harga ({cur})
          <span className="flex items-center gap-1">
            <input className={`${input} w-24`} inputMode="numeric" placeholder="min" value={f.priceMin} onChange={(e) => set({ priceMin: e.target.value.replace(/\D/g, "") })} />
            –
            <input className={`${input} w-24`} inputMode="numeric" placeholder="maks" value={f.priceMax} onChange={(e) => set({ priceMax: e.target.value.replace(/\D/g, "") })} />
          </span>
        </label>
        <label className="flex flex-col gap-1 text-xs text-ink2">Urutkan
          <span className="flex gap-1">
            <select className={input} value={f.sort} onChange={(e) => set({ sort: e.target.value })}>
              {Object.entries(SORT_FIELDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <button className={btn} title="Balik urutan" aria-label="Balik urutan" onClick={() => set({ order: f.order === "DESC" ? "ASC" : "DESC" })}>{f.order === "DESC" ? "↓" : "↑"}</button>
          </span>
        </label>
        <div className="flex flex-col gap-1 text-xs text-ink2">Kategori
          {f.category ? (
            <span className="flex h-9 items-center gap-2 rounded-md border border-line px-2.5 text-sm text-ink">{f.categoryName}
              <button aria-label="Hapus kategori" onClick={() => set({ category: "", categoryName: "" })}>✕</button>
            </span>
          ) : (
            <span className="flex gap-1">
              <input className={`${input} w-36`} placeholder="cari kategori" value={catQuery} onChange={(e) => setCatQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && searchCats()} />
              <button className={btn} onClick={searchCats}>Cari</button>
            </span>
          )}
        </div>
        <button className={`${btn} ml-auto`} disabled={!state.products.length} onClick={exportCsv}>Ekspor CSV</button>
        {!priceOk && <p className="w-full text-xs text-[var(--critical)]">Isi harga minimum dan maksimum sekaligus.</p>}
        {!f.category && (catMsg || cats?.length) ? (
          <div className="flex w-full flex-wrap items-center gap-2 text-sm">
            {catMsg && <span className="text-ink2">{catMsg}</span>}
            {cats?.map((c) => <button key={c.id} className="rounded-full border border-line px-3 py-1 hover:bg-page" onClick={() => { set({ category: c.id, categoryName: c.name }); setCats(null); setCatQuery(""); }}>{c.name}</button>)}
          </div>
        ) : null}
      </section>

      {state.error && !state.loading && (
        <div role="alert" className="mb-4 rounded-md border border-red-300 bg-red-50 px-3 py-3 text-sm text-red-900">
          <p className="font-medium">{{ auth: "API key bermasalah", quota: "Kuota atau paket tidak mencukupi", parameter: "Filter tidak valid", network: "Gangguan jaringan" }[state.error.kind] ?? "Gagal memuat data"}</p>
          <p className="mt-1">{state.error.message}</p>
          {!demo && <button className="mt-2 underline" onClick={() => { setDemo(true); setPicked([]); }}>Lihat tampilan dengan data demo</button>}
        </div>
      )}

      {/* Tren & perbandingan */}
      <section className="mb-4 rounded-lg border border-line bg-surface p-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-medium">Tren revenue harian {picked.length === 1 ? `— ${picked[0].product.product_name}` : picked.length > 1 ? `— ${picked.length} produk` : ""}</h2>
          <div className="flex gap-1" role="group" aria-label="Rentang tren">
            {DETAIL_RANGES.map((r) => (
              <button key={r} className={`h-8 rounded-md px-3 text-sm ${trendRange === r ? "bg-ink text-surface" : "border border-line text-ink2 hover:bg-page"}`} aria-pressed={trendRange === r} onClick={() => setTrendRange(r)}>{RANGE_LABEL[r]}</button>
            ))}
          </div>
        </div>
        {picked.length === 0 ? (
          <p className="py-10 text-center text-sm text-ink3">Centang hingga {MAX_COMPARE} produk di tabel untuk melihat tren dan membandingkannya.</p>
        ) : (
          <>
            {series.length > 0 ? <TrendChart series={series} currency={cur} /> : <p className="py-10 text-center text-sm text-ink3">{picked.some((p) => detailOf(p.product)?.loading) ? "Memuat tren…" : "Data tren tidak tersedia."}</p>}
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-ink2">
                  <tr><th className="py-1 pr-3 font-normal">Produk</th><th className="px-3 text-right font-normal">Skor</th><th className="px-3 text-right font-normal">Revenue ({RANGE_LABEL[f.range]})</th><th className="px-3 text-right font-normal">Unit</th><th className="px-3 text-right font-normal">Harga</th><th className="px-3 text-right font-normal">Komisi</th><th className="px-3 text-right font-normal">Pertumbuhan</th><th className="px-3 text-right font-normal">Total tren ({RANGE_LABEL[trendRange]})</th><th /></tr>
                </thead>
                <tbody>
                  {picked.map(({ product: p, slot }) => {
                    const d = detailOf(p);
                    return (
                      <tr key={p.product_id} className="border-t border-line">
                        <td className="max-w-xs py-2 pr-3"><span className="mr-2 inline-block h-0.5 w-4 align-middle" style={{ background: SERIES_COLORS[slot] }} /><span className="align-middle" title={p.product_name}>{p.product_name.length > 70 ? p.product_name.slice(0, 69) + "…" : p.product_name}</span></td>
                        <td className="num px-3 text-right">{p.score ?? "–"}</td>
                        <td className="num px-3 text-right">{fmtMoney(p.revenue, cur)}</td>
                        <td className="num px-3 text-right">{fmtNum(p.sales_volume)}</td>
                        <td className="num px-3 text-right">{fmtMoney(p.unit_price, cur)}</td>
                        <td className="num px-3 text-right">{fmtPct(p.commission_rate)}</td>
                        <td className="num px-3 text-right">{fmtPct(p.revenue_growth_rate, true)}</td>
                        <td className="num px-3 text-right">{d?.loading ? "…" : d?.error ? <span className="text-[var(--critical)]" title={d.error}>gagal</span> : d?.trend?.length ? fmtMoney(d.trend.reduce((a, x) => a + x.value, 0), cur) : "–"}</td>
                        <td className="pl-2 text-right"><button aria-label={`Hapus ${p.product_name}`} className="text-ink3 hover:text-ink" onClick={() => toggle(p)}>✕</button></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      {/* Tabel peringkat */}
      <section className="rounded-lg border border-line bg-surface">
        <div className="overflow-x-auto">
          <table className={`w-full text-sm ${state.loading ? "opacity-50" : ""}`}>
            <thead className="border-b border-line text-left text-xs text-ink2">
              <tr>
                <th className="w-10 p-3 font-normal"><span className="sr-only">Pilih</span></th>
                <th className="w-10 py-3 font-normal">#</th>
                <th className="py-3 font-normal">Produk</th>
                <th className="px-3 text-right font-normal" title="Skor relatif 0–100 buatan aplikasi: persentil di antara hasil yang tampil — revenue 35%, pertumbuhan 30%, unit 20%, komisi 15%.">Skor potensi ⓘ</th>
                <th className="px-3 text-right font-normal">Revenue</th>
                <th className="px-3 text-right font-normal">Unit</th>
                <th className="px-3 text-right font-normal">Harga</th>
                <th className="px-3 text-right font-normal">Komisi</th>
                <th className="px-3 text-right font-normal">Pertumbuhan</th>
              </tr>
            </thead>
            <tbody>
              {state.products.map((p, i) => {
                const on = picked.some((x) => x.product.product_id === p.product_id);
                const g = p.revenue_growth_rate;
                return (
                  <tr key={p.product_id} className="border-b border-line last:border-0 hover:bg-page">
                    <td className="p-3"><input type="checkbox" className="h-4 w-4" checked={on} disabled={!on && picked.length >= MAX_COMPARE} onChange={() => toggle(p)} aria-label={`Pilih ${p.product_name}`} /></td>
                    <td className="num text-ink3">{(f.page - 1) * 20 + i + 1}</td>
                    <td className="py-2">
                      <div className="flex items-center gap-3">
                        {p.master_image_url ? <img src={p.master_image_url} alt="" referrerPolicy="no-referrer" className="h-10 w-10 rounded object-cover" /> : <div className="h-10 w-10 rounded bg-page" />}
                        <div className="min-w-0"><div className="max-w-md truncate">{p.product_name}</div><div className="text-xs text-ink3">ID {p.product_id}{p.launch_date ? ` · rilis ${p.launch_date}` : ""}</div></div>
                      </div>
                    </td>
                    <td className="px-3">
                      <div className="flex items-center justify-end gap-2"><div className="h-1.5 w-16 rounded-full bg-page"><div className="h-1.5 rounded-full bg-accent" style={{ width: `${p.score ?? 0}%` }} /></div><span className="num w-7 text-right">{p.score ?? "–"}</span></div>
                    </td>
                    <td className="num px-3 text-right">{fmtMoney(p.revenue, cur)}</td>
                    <td className="num px-3 text-right">{fmtNum(p.sales_volume)}</td>
                    <td className="num px-3 text-right">{fmtMoney(p.unit_price, cur)}</td>
                    <td className="num px-3 text-right">{fmtPct(p.commission_rate)}</td>
                    <td className="num px-3 text-right" style={{ color: g == null || g === 0 ? undefined : g > 0 ? "var(--good)" : "var(--critical)" }}>{g == null ? "–" : `${g > 0 ? "▲" : g < 0 ? "▼" : ""} ${fmtPct(g, true)}`}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {!state.products.length && <p className="p-10 text-center text-sm text-ink3">{state.loading ? "Memuat produk…" : state.error ? "Tidak ada data untuk ditampilkan." : "Tidak ada produk yang cocok. Coba longgarkan filter."}</p>}
        <div className="flex items-center justify-between border-t border-line p-3 text-sm text-ink2">
          <span>Halaman {f.page} dari maks. 5</span>
          <span className="flex gap-2">
            <button className={btn} disabled={f.page <= 1 || state.loading} onClick={() => setF((p) => ({ ...p, page: p.page - 1 }))}>← Sebelumnya</button>
            <button className={btn} disabled={f.page >= 5 || state.products.length < 20 || state.loading} onClick={() => setF((p) => ({ ...p, page: p.page + 1 }))}>Berikutnya →</button>
          </span>
        </div>
      </section>
      <p className="mt-3 text-xs text-ink3">Skor potensi adalah peringkat relatif di antara produk yang sedang tampil, bukan prediksi penjualan. Selalu cek tren sebelum memutuskan.</p>
    </main>
  );
}
