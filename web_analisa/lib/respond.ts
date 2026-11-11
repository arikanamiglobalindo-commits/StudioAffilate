import "server-only";
import { NextResponse } from "next/server";
import { KaloError } from "./kalodata";
import type { ApiResult } from "./types";

const STATUS = { auth: 401, quota: 429, parameter: 400, network: 502, upstream: 502 } as const;

export function ok<T>(data: T, demo: boolean, cached: boolean) {
  return NextResponse.json({ ok: true, data, demo, cached } satisfies ApiResult<T>);
}

export function fail(e: unknown) {
  if (e instanceof KaloError) {
    return NextResponse.json({ ok: false, kind: e.kind, message: e.message } satisfies ApiResult<never>, { status: STATUS[e.kind] });
  }
  console.error(e);
  return NextResponse.json({ ok: false, kind: "upstream", message: "Terjadi kesalahan internal." } satisfies ApiResult<never>, { status: 500 });
}

export function bad(message: string) {
  return NextResponse.json({ ok: false, kind: "parameter", message } satisfies ApiResult<never>, { status: 400 });
}

export const isDemo = (sp: URLSearchParams) => sp.get("demo") === "1" || process.env.KALODATA_MOCK === "1";
