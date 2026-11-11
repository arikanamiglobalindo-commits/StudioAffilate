import { kalo } from "@/lib/kalodata";
import { fail, ok } from "@/lib/respond";

export async function GET() {
  try {
    const { data, cached } = await kalo("/credit/balance", {}, "GET");
    const d = (data ?? {}) as Record<string, unknown>;
    return ok({ total: d.totalRemain ?? null }, false, cached);
  } catch (e) {
    return fail(e);
  }
}
