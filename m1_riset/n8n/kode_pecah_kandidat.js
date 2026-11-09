// Node "Code" (mode: Run Once for All Items) — ubah daftar kandidat jadi baris Data Table.
// Hanya 30 teratas agar tabel tidak membengkak.
const d = $input.first().json;
if (d.status !== 'ok') return [];
return (d.kandidat || []).slice(0, 30).map(k => ({
  json: {
    ...k,
    saran_handle_seller: (k.saran_handle_seller || []).join(', '),
    omzet_akun_toko: k.omzet_akun_toko ?? -1,   // -1 = belum dicek
  }
}));
