// Klien server-side untuk Kalodata Open API. File ini hanya boleh diimpor dari
// route handler: API key dibaca dari environment dan tidak pernah dikirim ke browser.
import "server-only";
import type { ApiErrorKind } from "./types";

const BASE_URL = (process.env.KALODATA_BASE_URL ?? "https://www.kalodata.com/openapi/v1").replace(/\/$/, "");
const CACHE_TTL_MS = Number(process.env.KALODATA_CACHE_TTL_SECONDS ?? 900) * 1000;
const RETRIES = 3;

export class KaloError extends Error {
  constructor(public kind: ApiErrorKind, message: string) {
    super(message);
  }
}

type Entry = { at: number; data: unknown };
const g = globalThis as unknown as { __kaloCache?: Map<string, Entry>; __kaloInflight?: Map<string, Promise<unknown>> };
const cache = (g.__kaloCache ??= new Map());
const inflight = (g.__kaloInflight ??= new Map());

function translate(code: string, message: string): KaloError {
  const low = message.toLowerCase();
  // Kalodata melaporkan key bermasalah sebagai HTTP 200 + code 501.
  if (code === "501" && low.startsWith("the key")) {
    return new KaloError("auth", `Kalodata menolak API key: "${message}". Periksa key di Kalodata Open Center.`);
  }
  if (code === "2016") {
    const isParam = ["must be", "invalid", "required", "for input string", "parameter"].some((h) => low.includes(h));
    return isParam
      ? new KaloError("parameter", `Parameter ditolak Kalodata: ${message}`)
      : new KaloError("quota", `Batas paket/kuota Kalodata: ${message}`);
  }
  return new KaloError("upstream", `Kalodata mengembalikan error: ${message || "tidak diketahui"}`);
}

async function callOnce(path: string, body: unknown, method: "GET" | "POST"): Promise<unknown> {
  let res: Response;
  try {
    res = await fetch(BASE_URL + path, {
      method,
      headers: {
        "Content-Type": "application/json;charset=UTF-8",
        // Di lingkungan dengan proxy yang menyuntikkan kredensial, nilai ini diganti oleh proxy.
        "secret-key": process.env.KALODATA_API_KEY ?? "proxy-injected",
      },
      body: method === "POST" ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(30_000),
      cache: "no-store",
    });
  } catch (e) {
    throw new KaloError("network", `Tidak bisa menghubungi Kalodata (${(e as Error).message})`);
  }
  if (res.status >= 500) throw new KaloError("network", `Kalodata HTTP ${res.status}`);
  let env: { success?: boolean; data?: unknown; code?: unknown; message?: unknown };
  try {
    env = await res.json();
  } catch {
    throw new KaloError(res.status === 403 || res.status === 401 ? "auth" : "network", `Respons Kalodata bukan JSON (HTTP ${res.status})`);
  }
  if (env?.success) return env.data;
  const code = String(env?.code ?? "");
  const message = String(env?.message ?? "");
  if (code === "2000" || message.toLowerCase().includes("acquire connection timeout")) {
    throw new KaloError("network", message || "timeout di sisi Kalodata");
  }
  if (/not found|未找到/i.test(message)) return null; // hasil kosong yang sah
  throw translate(code, message);
}

/** Memanggil Kalodata dengan cache in-memory + dedup + retry, supaya kuota tidak terbuang. */
export async function kalo(path: string, body: unknown = {}, method: "GET" | "POST" = "POST"): Promise<{ data: unknown; cached: boolean }> {
  const key = `${method} ${path} ${JSON.stringify(body)}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < CACHE_TTL_MS) return { data: hit.data, cached: true };

  const pending = inflight.get(key);
  if (pending) return { data: await pending, cached: true };

  const run = (async () => {
    let last: KaloError | undefined;
    for (let i = 0; i < RETRIES; i++) {
      try {
        return await callOnce(path, body, method);
      } catch (e) {
        if (!(e instanceof KaloError) || e.kind !== "network") throw e;
        last = e;
        await new Promise((r) => setTimeout(r, 300 * (i + 1)));
      }
    }
    throw last!;
  })();
  inflight.set(key, run);
  try {
    const data = await run;
    cache.set(key, { at: Date.now(), data });
    if (cache.size > 500) cache.delete(cache.keys().next().value!);
    return { data, cached: false };
  } finally {
    inflight.delete(key);
  }
}

export function asList(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data;
  const inner = (data as { data?: unknown } | null)?.data;
  if (Array.isArray(inner)) return inner;
  return [];
}
