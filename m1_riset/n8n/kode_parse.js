// Node "Code" (mode: Run Once for All Items) — tempel di n8n.
// Varian A (Execute Command): hasil skrip ada di $json.stdout
// Varian B (Webhook): hasil skrip ada di $json.body
const item = $input.first().json;
let d = item.body ?? null;
if (!d) {
  const baris = String(item.stdout || '').trim().split('\n');
  d = JSON.parse(baris[baris.length - 1]);   // skrip mencetak SATU baris JSON di akhir
}
return [{ json: d }];
