"""
app.py — Modul M1 Riset Produk (Streamlit).

Jalankan di Windows (PowerShell, di folder proyek):
    .venv\\Scripts\\activate
    streamlit run app.py

Alur 4 langkah (menu kiri):
  1. Impor Kalodata   -> Risiko AKSES DATA
  2. Filter & Skor    -> Risiko TIMING TREN
  3. Footage 4 Adegan -> Risiko HAK FOOTAGE
  4. Gerbang & Kirim  -> ketiganya, lalu kirim ke antrean n8n
"""
import os
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from m1 import config, db, gate, importer, n8n_client, otomatis, pipeline, sumber_api
from m1.kalodata_api import BASE_URL, KalodataAPI, KalodataError
from m1.filters import corong, rata_komisi_kategori_opsional
from m1.footage import (ambil_oembed, daftar_handle, link_pencarian, ringkas_kelengkapan,
                        tentukan_status_hak, validasi_klip)
from m1.parsing import format_rupiah, parse_timestamp

load_dotenv()
st.set_page_config(page_title="M1 Riset Produk", page_icon="🔎", layout="wide")
HASIL_PKL = Path(db.DB_PATH).parent / "hasil_terakhir.pkl"

# ---------------------------------------------------------------- state awal
ss = st.session_state
# Nilai widget disimpan di session_state. Trik "ss[k] = ss[k]" mencegah Streamlit
# menghapus nilai widget saat Anda pindah halaman (widget tidak tampil).
AWAL_WIDGET = {**{f"f_{k}": v for k, v in config.DEFAULT_FILTER.items()},
               **{f"kat_{k}": True for k in config.KATEGORI_UTAMA},
               **{f"kat_{k}": False for k in config.KATEGORI_OPSIONAL},
               **{f"b_{k}": v for k, v in config.BOBOT_SKOR.items()},
               "api_key": os.getenv("KALODATA_API_KEY", ""),
               "api_max_panggilan": config.API_DEFAULT["max_panggilan"]}
for k, v in AWAL_WIDGET.items():
    ss[k] = ss[k] if k in ss else v


def reset_blueprint():
    """Callback tombol reset (harus callback agar boleh mengubah nilai widget)."""
    for k, v in config.DEFAULT_FILTER.items():
        ss[f"f_{k}"] = v

ss.setdefault("df_norm", None)
ss.setdefault("tanggal_data", date.today().isoformat())
if "hasil" not in ss:
    # Pulihkan hasil run terakhir agar tidak hilang saat aplikasi ditutup
    try:
        ss["hasil"] = pd.read_pickle(HASIL_PKL) if HASIL_PKL.exists() else None
    except Exception:  # file dari versi pandas lain -> abaikan, jalankan riset ulang
        ss["hasil"] = None


def label_risiko(teks: str):
    st.caption(f"🛡️ Risiko yang ditangani: **{teks}**")


menu = st.sidebar.radio("Langkah", ["1. Ambil Data Kalodata", "2. Filter & Skor",
                                    "3. Footage 4 Adegan", "4. Gerbang & Kirim n8n"])
st.sidebar.divider()
st.sidebar.caption("Data lokal: " + str(db.DB_PATH))

# =================================================================== 1. AMBIL DATA
def buat_api():
    """Klien API dengan cache harian (run ulang hari yang sama = gratis)."""
    return KalodataAPI(ss.get("api_key", ""), base_url=os.getenv("KALODATA_BASE_URL") or BASE_URL,
                       max_panggilan=int(ss.get("api_max_panggilan", config.API_DEFAULT["max_panggilan"])),
                       cache_dir=Path(db.DB_PATH).parent / "api_cache")


def bagian_api():
    with st.expander("Cara dapat API key", expanded=not ss["api_key"]):
        st.markdown("1. Login ke **kalodata.com/open-center/account**, lalu klik **Generate key**.\n"
                    "2. Tempel kunci ke file `.env` sebagai `KALODATA_API_KEY=...` (atau isi kolom di bawah).\n"
                    "3. Cek **harga kredit** di Open Center. API memakai kredit per panggilan. "
                    "Modul ini membatasi panggilan per run dan meng-cache hasil per hari.")
    st.text_input("API key Kalodata", type="password", key="api_key")
    if not ss["api_key"]:
        st.stop()

    # --- tes 1 panggilan
    if st.button("🔌 Tes API & cek saldo (1 panggilan = 0,1 kredit)"):
        try:
            api = buat_api()
            st.write("Saldo kredit:", api.saldo())  # gratis
            contoh = api.product_rank(page_size=5, hanya_affiliate=False)
            st.write(f"Contoh ranking produk Indonesia ({len(contoh)} baris). Baris pertama mentah:")
            st.json(contoh[0] if contoh else {})
        except KalodataError as e:
            st.error(f"[{e.jenis}] {e}")

    # --- kategori
    st.subheader("a) Kategori Kalodata")
    kat = sumber_api.baca_kategori()
    ikut_opsional = st.checkbox("Ikut cari kategori opsional (Kecantikan, Ibu & Bayi, Hewan) untuk cek komisi ≥10%",
                                value=False)
    labels = set(config.KATA_CARI_KATEGORI) if ikut_opsional else config.LABEL_API_UTAMA
    n_cari = sum(len(v) for k, v in config.KATA_CARI_KATEGORI.items() if k in labels)
    if st.button(f"🔎 Cari ID kategori (sekali saja, {n_cari} panggilan = {n_cari * config.BIAYA_PER_PANGGILAN:.1f} kredit)"):
        try:
            kat = sumber_api.resolusi_kategori(buat_api(), labels=labels)
            sumber_api.simpan_kategori(kat)
        except KalodataError as e:
            st.error(f"[{e.jenis}] {e}")
    if kat.empty:
        st.info("Belum ada ID kategori. Klik tombol di atas.")
        st.stop()
    st.caption("Centang 'pakai' hanya untuk kategori yang sesuai blueprint. Kategori opsional "
               "(Kecantikan, Ibu & Bayi, Hewan) hanya untuk mengecek rata-rata komisi.")
    kat = st.data_editor(kat, hide_index=True, width="stretch", disabled=["label_m1", "kata_cari",
                                                                            "category_id", "nama", "level"])
    if st.button("💾 Simpan pilihan kategori"):
        sumber_api.simpan_kategori(kat)
        st.success("Tersimpan.")

    # --- pengaturan kredit
    st.subheader("b) Tarik data (periode 7 hari terakhir, region ID, IDR)")
    c1, c2, c3 = st.columns(3)
    halaman = c1.number_input("Halaman per kategori (×100 produk)", 1, 5, config.API_DEFAULT["halaman"])
    max_kandidat = c2.number_input("Maks produk diambil detailnya", 10, 300, config.API_DEFAULT["max_kandidat"])
    c3.number_input("Batas panggilan per run (pengaman kredit)", 20, 2000, key="api_max_panggilan")
    saring_server = st.checkbox("Saring harga & omzet di server (hemat kredit)", value=True,
                                help="Sudah terbukti bekerja dalam Rupiah pada akun Anda.")
    ambil_toko = st.checkbox("Ambil nama toko sekarang (+0,1 kredit per toko)", value=False,
                             help="Kalau dimatikan, toko tampil sebagai shop:ID. Nama toko bisa diambil "
                                  "per produk di Langkah 3, cukup untuk produk teratas saja.")
    n_kat = int(kat["pakai"].sum())
    maks = n_kat * halaman + max_kandidat * (2 if ambil_toko else 1)
    st.caption(f"Perkiraan maksimal: {n_kat} kategori × {halaman} halaman + {max_kandidat} detail produk"
               f"{' + toko' if ambil_toko else ''} ≈ **≤ {maks} panggilan ≈ ≤ "
               f"{maks * config.BIAYA_PER_PANGGILAN:.1f} kredit**. Data yang sama di hari yang sama diambil dari cache (gratis).")
    try:
        st.caption(f"Saldo kredit saat ini: **{buat_api().saldo().get('totalRemain', '?')}**")
    except KalodataError as e:
        st.caption(f"Saldo tidak terbaca: {e}")

    if st.button("⬇️ Tarik data produk", type="primary"):
        f = {k: ss[f"f_{k}"] for k in config.DEFAULT_FILTER}
        bar = st.progress(0.0, "Mulai...")
        try:
            api = buat_api()
            df, catatan = sumber_api.tarik_produk(
                api, kat, f, halaman=halaman, saring_server=saring_server,
                max_kandidat=max_kandidat, ambil_toko=ambil_toko,
                progress=lambda x, t: bar.progress(min(x, 1.0), t))
        except KalodataError as e:
            st.error(f"[{e.jenis}] {e}")
            st.stop()
        for c in catatan:
            st.write("• " + c)
        if df.empty:
            st.stop()
        ss["df_norm"] = df
        ss["tanggal_data"] = date.today().isoformat()
        st.success(f"{len(df)} produk siap (data {ss['tanggal_data']}). Lanjut ke langkah 2.")
        st.dataframe(df[["nama", "toko", "kategori_teks", "harga", "omzet_7h", "pertumbuhan_pct",
                         "jumlah_creator", "komisi_pct"]].head(20), width="stretch")


def bagian_csv():
    st.caption("Cadangan bila API bermasalah atau kredit habis.")
    with st.expander("Cara export dari Kalodata (manual, aman)", expanded=False):
        st.markdown(
            "1. Buka Kalodata → **Produk** → atur periode **7 hari terakhir** dan negara **Indonesia**.\n"
            "2. Klik **Export** → simpan file CSV/XLSX.\n"
            "3. Ulangi tiap minggu di hari yang sama, agar modul bisa membandingkan tren (snapshot).")
    berkas = st.file_uploader("Unggah file export (CSV / XLSX)", type=["csv", "xlsx", "xls"])
    ss["tanggal_data"] = st.date_input("Tanggal akhir periode data", value=date.fromisoformat(
        ss["tanggal_data"])).isoformat()
    if not berkas:
        return
    mentah = importer.baca_file(berkas, berkas.name)
    st.write(f"**{len(mentah)} baris**, {len(mentah.columns)} kolom terbaca.")
    tebakan = importer.tebak_pemetaan(mentah.columns)
    st.subheader("Pemetaan kolom")
    st.caption("Dicocokkan otomatis. Periksa hasilnya; kalau salah, pilih kolom yang benar. Tanda * = wajib.")
    opsi = ["(tidak ada)"] + list(mentah.columns)
    pemetaan, cols = {}, st.columns(3)
    for i, internal in enumerate(config.ALIAS_KOLOM):
        wajib = "*" if internal in config.KOLOM_WAJIB else ""
        awal = tebakan.get(internal)
        pilih = cols[i % 3].selectbox(f"{internal}{wajib}", opsi,
                                      index=opsi.index(awal) if awal in opsi else 0,
                                      key=f"map_{berkas.name}_{internal}")
        if pilih != "(tidak ada)":
            pemetaan[internal] = pilih
    df_norm, warn = importer.normalisasi(mentah, pemetaan)
    for w in warn:
        st.warning(w)
    hilang = [k for k in config.KOLOM_WAJIB if k not in pemetaan]
    st.subheader("Pratinjau hasil baca (cek angka masuk akal!)")
    st.dataframe(df_norm[[c for c in ["nama", "toko", "kategori_teks", "harga", "omzet_7h",
                                      "pertumbuhan_pct", "jumlah_creator", "komisi_pct"]
                          if c in df_norm]].head(15), width="stretch")
    if hilang:
        st.error("Lengkapi kolom wajib dulu: " + ", ".join(hilang))
    elif st.button("✅ Gunakan data ini", type="primary"):
        ss["df_norm"] = df_norm
        st.success(f"{len(df_norm)} produk siap. Lanjut ke langkah 2.")


if menu.startswith("1"):
    st.title("1. Ambil data Kalodata — tab Produk")
    label_risiko("Akses Data — Open API resmi (atau export manual), tanpa scraping")
    tgl = db.daftar_tanggal_snapshot()
    st.info("Snapshot tersimpan: " + (", ".join(tgl) if tgl else "belum ada") +
            " — butuh ≥2 snapshot berjarak ~7 hari untuk deteksi lewat puncak & lonjakan creator.")
    sumber = st.radio("Sumber data", ["Kalodata API (utama)", "Export CSV (cadangan)"], horizontal=True)
    if sumber.startswith("Kalodata API"):
        bagian_api()
    else:
        bagian_csv()

# ============================================================ 2. FILTER & SKOR
elif menu.startswith("2"):
    st.title("2. Filter & Skor")
    label_risiko("Timing Tren — pertumbuhan, kepadatan creator, perbandingan snapshot")
    df_norm = ss["df_norm"]
    if df_norm is None:
        st.warning("Impor data dulu di langkah 1.")
        st.stop()

    with st.sidebar:
        st.header("Enam filter")
        c1, c2 = st.columns(2)
        c1.number_input("Harga min (Rp)", step=5_000, key="f_harga_min")
        c2.number_input("Harga maks (Rp)", step=5_000, key="f_harga_max")
        c1.number_input("Omzet 7h min (Rp)", step=1_000_000, key="f_omzet7_min")
        c2.number_input("Omzet 7h maks (Rp)", step=1_000_000, key="f_omzet7_max")
        st.number_input("Pertumbuhan omzet min (%)", step=5.0, key="f_growth_min")
        c1, c2 = st.columns(2)
        c1.number_input("Creator min", step=1, key="f_creator_min")
        c2.number_input("Creator maks", step=1, key="f_creator_max")
        st.number_input("Komisi min (%)", step=0.5, key="f_komisi_min")
        st.button("↺ Kembalikan ke blueprint", on_click=reset_blueprint)

        st.header("Kategori")
        kategori_aktif = {}
        for nama, kunci in config.KATEGORI_UTAMA.items():
            if st.checkbox(nama, key=f"kat_{nama}"):
                kategori_aktif[nama] = kunci
        tabel_ops = rata_komisi_kategori_opsional(df_norm)
        st.caption(f"Kategori tambahan hanya bisa dicentang bila rata-rata komisinya "
                   f"≥ {config.AMBANG_KOMISI_TAMBAHAN:.0f}% di data ini (min 5 produk).")
        for _, r in tabel_ops.iterrows():
            info = f"{r['kategori']} (rata {r['rata_komisi_pct']}%, {r['jumlah_produk']} produk)"
            if not r["boleh_diaktifkan"]:
                ss[f"kat_{r['kategori']}"] = False  # dikunci: komisi rata-rata < ambang
            if st.checkbox(info, disabled=not r["boleh_diaktifkan"], key=f"kat_{r['kategori']}"):
                kategori_aktif[r["kategori"]] = config.KATEGORI_OPSIONAL[r["kategori"]]

        st.header("Bobot skor")
        bobot = {k: st.slider(k, 0.0, 1.0, step=0.05, key=f"b_{k}") for k in config.BOBOT_SKOR}

    filter_nilai = {k: ss[f"f_{k}"] for k in config.DEFAULT_FILTER}
    if filter_nilai != config.DEFAULT_FILTER:
        st.warning("⚠️ Filter berbeda dari blueprint 12 minggu. Catat alasannya sebelum dipakai.")

    if st.button("▶️ Jalankan riset", type="primary"):
        hasil = pipeline.jalankan(df_norm, ss["tanggal_data"], filter_nilai, kategori_aktif, bobot)
        hasil.attrs["tanggal_data"] = ss["tanggal_data"]
        ss["hasil"] = hasil
        hasil.to_pickle(HASIL_PKL)

    hasil = ss["hasil"]
    if hasil is None:
        st.stop()
    lolos = hasil[hasil["lolos"]].sort_values("skor_akhir", ascending=False)
    n = len(lolos)
    (st.success if n >= config.TARGET_PRODUK_LOLOS else st.error)(
        f"{n} produk lolos (target ≥ {config.TARGET_PRODUK_LOLOS}) — data {hasil.attrs.get('tanggal_data', '')}")
    kiri, kanan = st.columns([1, 2])
    with kiri:
        st.subheader("Corong filter")
        st.dataframe(corong(hasil), hide_index=True, width="stretch")
        if n < config.TARGET_PRODUK_LOLOS:
            st.markdown("**Kurang dari target?** Jangan langsung melonggarkan filter. Pertama "
                        "export lebih banyak baris (lebih banyak halaman / sub-kategori). Kolom "
                        "'gagal_di_filter_ini_saja' menunjukkan filter mana yang paling memotong. "
                        "Pakai API? Naikkan 'Maks produk diambil detailnya' atau 'Halaman per kategori' "
                        "di Langkah 1. Produk tanpa detail tercatat gagal di filter creator.")
    with kanan:
        st.subheader("Produk lolos + skor")
        tampil = lolos[["nama", "toko", "kategori_m1", "harga", "omzet_7h", "pertumbuhan_pct",
                        "jumlah_creator", "komisi_pct", "skor_komisi", "skor_pertumbuhan",
                        "skor_kepadatan", "penalti_tren", "skor_akhir", "flag_tren", "sumber_growth"]].copy()
        tampil["harga"] = tampil["harga"].map(format_rupiah)
        tampil["omzet_7h"] = tampil["omzet_7h"].map(format_rupiah)
        tampil["flag_tren"] = tampil["flag_tren"].map(", ".join)
        st.dataframe(tampil, hide_index=True, width="stretch",
                     column_config={"skor_akhir": st.column_config.ProgressColumn(
                         "skor_akhir", min_value=0, max_value=100, format="%.1f")})
        st.download_button("⬇️ Unduh CSV produk lolos", lolos.drop(columns=["flag_tren"]).assign(
            flag_tren=lolos["flag_tren"].map(",".join)).to_csv(index=False).encode("utf-8-sig"),
            "m1_produk_lolos.csv", "text/csv")
    with st.expander("Produk gagal & alasannya"):
        st.dataframe(hasil[~hasil["lolos"]][["nama", "kategori_teks", "alasan_gagal"]],
                     hide_index=True, width="stretch")

# =========================================================== 3. FOOTAGE
elif menu.startswith("3"):
    st.title("3. Footage 4 adegan")
    label_risiko("Hak Footage — seller dulu, affiliate lain hanya cadangan & ditandai berisiko")
    hasil = ss["hasil"]
    if hasil is None:
        st.warning("Jalankan riset dulu di langkah 2.")
        st.stop()
    lolos = hasil[hasil["lolos"]].sort_values("skor_akhir", ascending=False)
    if lolos.empty:
        st.warning("Belum ada produk lolos.")
        st.stop()

    semua_footage = db.baca_footage()
    ring = ringkas_kelengkapan(semua_footage, lolos["produk_id"])
    st.subheader("Kelengkapan footage semua produk lolos")
    st.dataframe(lolos[["produk_id", "nama", "skor_akhir"]].merge(ring, on="produk_id"),
                 hide_index=True, width="stretch")

    status_auto = {k: v.get("status") for k, v in otomatis.baca_scout().items()}
    ikon_auto = {"siap_isi_timestamp": "🟢 ", "tanpa_footage_seller": "⚪ "}
    # Produk yang siap isi timestamp (hasil run otomatis) ditaruh paling atas
    lolos = lolos.assign(_siap=lolos["produk_id"].map(lambda p: status_auto.get(str(p)) == "siap_isi_timestamp")) \
        .sort_values(["_siap", "skor_akhir"], ascending=[False, False])
    label_pilih = {r.produk_id: f"{ikon_auto.get(status_auto.get(str(r.produk_id)), '')}[{r.skor_akhir:.0f}] "
                                f"{r.nama} — {r.toko}" for r in lolos.itertuples()}
    pid = st.selectbox("Pilih produk", list(label_pilih), format_func=label_pilih.get)
    prod = lolos[lolos["produk_id"] == pid].iloc[0]

    # Nama toko on-demand (hemat kredit: hanya untuk produk yang sedang dikerjakan)
    if str(prod["toko"]).startswith("shop:") and ss.get("api_key"):
        if st.button("🏪 Ambil nama toko (0,1 kredit)"):
            try:
                sid = prod["toko"].split(":", 1)[1]
                sd = buat_api().shop_detail(sid)
                nama = sd.get("shop_name") or sd.get("name")
                if nama:
                    sumber_api.simpan_info_toko(sd)
                if nama:
                    h = ss["hasil"]
                    h.loc[h["toko"] == prod["toko"], "toko"] = nama
                    h.to_pickle(HASIL_PKL)
                    st.rerun()
                st.warning("Kalodata tidak mengirim nama toko.")
            except KalodataError as e:
                st.error(f"[{e.jenis}] {e}")

    info = sumber_api.baca_info_toko(prod["toko"])
    if info:
        sendiri = info.get("self_account_revenue") or 0
        if sendiri > 0:
            st.success(f"Toko punya akun sendiri yang berjualan (omzet akun sendiri {format_rupiah(sendiri)}), "
                       "jadi peluang ada footage seller.")
        else:
            st.warning("Omzet akun milik toko = Rp0, artinya toko hampir pasti tidak membuat video sendiri. "
                       "Minta materi video mentah lewat chat toko, atau pilih produk lain.")

    # Hasil run otomatis (n8n): status footage & saran handle seller, tanpa memakai kredit
    scout = otomatis.baca_scout().get(str(pid), {})
    peta = db.peta_handle_seller()
    if scout:
        st.caption(f"Run otomatis: status **{scout.get('status')}** {scout.get('alasan', '')}")
        saran_auto = scout.get("saran_handle_seller") or []
        if saran_auto and not peta.get(prod["toko"]):
            st.info("Saran handle seller dari run otomatis: " + ", ".join("@" + h for h in saran_auto) +
                    ". Buka profilnya dan pastikan itu akun RESMI toko sebelum dikonfirmasi.")
            if st.button("✅ Saya sudah cek: konfirmasi sebagai akun resmi seller"):
                db.set_handle_seller(prod["toko"], ", ".join(saran_auto))
                st.rerun()

    st.markdown("#### a) Akun TikTok resmi seller")
    handle_teks = st.text_input(f"Handle resmi toko **{prod['toko']}** (pisahkan koma)",
                                value=peta.get(prod["toko"], ""),
                                help="Cek dari halaman toko di TikTok Shop → profil penjual. "
                                     "Video dari handle ini = footage seller.")
    if st.button("Simpan handle seller"):
        db.set_handle_seller(prod["toko"], handle_teks)
        st.success("Tersimpan.")
    handle_seller = daftar_handle(handle_teks)

    st.markdown("#### b) Cari footage (urut prioritas)")
    for lbl, url in link_pencarian(prod["nama"], prod["toko"], handle_seller,
                                   prod.get("url_produk", "")).items():
        st.markdown(f"- [{lbl}]({url})")

    # Video: dari run otomatis (gratis, sudah tersimpan) atau ambil langsung via API (0,1 kredit)
    kunci_v = f"video_{pid}"
    if ss.get(kunci_v) is None and scout.get("video_seller"):
        ss[kunci_v] = pd.DataFrame(scout["video_seller"]).assign(judul="", omzet=None, video_ai=0)
    if ss.get("api_key") and st.button("🎬 Ambil daftar video lengkap dari Kalodata (0,1 kredit)"):
        try:
            ss[kunci_v] = sumber_api.video_produk(buat_api(), pid, handle_seller)
        except KalodataError as e:
            st.error(f"[{e.jenis}] {e}")
    vid = ss.get(kunci_v)
    if vid is not None and not vid.empty:
        vid = vid.assign(sumber=vid["handle"].map(
            lambda h: "seller" if h in handle_seller else "affiliate_lain"))
        saran = sumber_api.saran_handle_seller(vid, prod["toko"])
        if saran and not handle_seller and not scout.get("saran_handle_seller"):
            st.info("Kemungkinan handle seller (CEK MANUAL di profil toko): " + ", ".join("@" + x for x in saran))
        st.dataframe(vid, hide_index=True, width="stretch",
                     column_config={"url": st.column_config.LinkColumn("url")})
        if (vid["video_ai"].astype(str).str.lower().isin(["1", "true"])).any():
            st.caption("Kolom video_ai = 1 berarti video buatan AI. Hindari sebagai footage 'asli'.")

        # Kunci widget berganti tiap klip tersimpan, jadi video yang sama bisa dipilih lagi
        # untuk adegan lain (timestamp berbeda).
        kunci_pilih = f"pilih_video_{ss.get('n_klip', 0)}"

        def pakai_video():
            ss[f"url_klip_{ss.get('n_klip', 0)}"] = ss[kunci_pilih]
        st.selectbox("Isi URL klip dari daftar ini", [""] + vid["url"].tolist(), key=kunci_pilih,
                     on_change=pakai_video,
                     format_func=lambda u: u and f"{vid.set_index('url').loc[u, 'sumber']} · {u}")
    elif vid is not None:
        st.info("Kalodata tidak punya video untuk produk ini.")

    st.markdown("#### c) Tambah klip per adegan")
    # Tanpa st.form: setiap klip tersimpan, kunci widget berganti (n) sehingga isian kosong lagi.
    n = ss.get("n_klip", 0)
    with st.container(border=True):
        adg = st.selectbox("Adegan", list(config.ADEGAN), format_func=lambda a: config.ADEGAN[a], key=f"adg_{n}")
        url = st.text_input("URL video TikTok", key=f"url_klip_{n}")
        c1, c2 = st.columns(2)
        mulai = c1.text_input("Mulai (mm:ss)", placeholder="0:03", key=f"mulai_{n}")
        selesai = c2.text_input("Selesai (mm:ss)", placeholder="0:08", key=f"selesai_{n}")
        bukti = st.text_input("Bukti izin seller (link chat / nama file screenshot) — opsional", key=f"bukti_{n}")
        catatan = st.text_input("Catatan (apa yang terlihat di klip)", key=f"cat_{n}")
        kirim_form = st.button("Cek & simpan klip", key=f"simpan_{n}")
    if kirim_form:
        t0, t1 = parse_timestamp(mulai), parse_timestamp(selesai)
        err = validasi_klip(t0, t1)
        if not url.startswith("http"):
            err.insert(0, "URL tidak valid")
        if err:
            st.error(" • ".join(err))
        else:
            with st.spinner("Cek pemilik video lewat TikTok oEmbed resmi..."):
                info = ambil_oembed(url)
            if info["error"]:
                st.warning(info["error"] + " — handle diambil dari URL bila ada.")
            status = tentukan_status_hak(info["handle"], handle_seller, bukti)
            db.tambah_footage({"produk_id": pid, "adegan": adg, "url": url, "mulai": t0, "selesai": t1,
                               "creator_handle": info["handle"], "status_hak": status,
                               "bukti_izin": bukti, "catatan": catatan or info["judul"][:120]})
            ss["n_klip"] = ss.get("n_klip", 0) + 1
            st.toast(f"Tersimpan: @{info['handle'] or '?'} → {config.STATUS_HAK[status]}")
            st.rerun()

    st.markdown("#### d) Klip tersimpan untuk produk ini")
    fp = db.baca_footage(pid)
    if fp.empty:
        st.info("Belum ada klip.")
    else:
        for r in fp.itertuples():
            ikon = {"seller_izin": "🟢", "seller": "🟡", "affiliate_berisiko": "🔴"}.get(r.status_hak, "⚪")
            c1, c2 = st.columns([6, 1])
            c1.markdown(f"{ikon} **{r.adegan}** · [{r.url[:60]}]({r.url}) · {r.mulai:.1f}s–{r.selesai:.1f}s "
                        f"· @{r.creator_handle or '?'} · {config.STATUS_HAK.get(r.status_hak, r.status_hak)}")
            if c2.button("Hapus", key=f"hapus_{r.id}"):
                db.hapus_footage(r.id)
                st.rerun()

# =========================================================== 4. GERBANG
else:
    st.title("4. Gerbang Keputusan & kirim ke n8n")
    label_risiko("Akses Data + Timing Tren + Hak Footage (semuanya dicek di sini)")
    hasil = ss["hasil"]
    if hasil is None:
        st.warning("Jalankan riset dulu di langkah 2.")
        st.stop()
    tanggal_data = hasil.attrs.get("tanggal_data", ss["tanggal_data"])
    ev = gate.evaluasi(hasil, db.baca_footage(), config.TOP_N_GERBANG)
    if ev.empty:
        st.warning("Belum ada produk lolos.")
        st.stop()
    n_kirim = int((ev["keputusan"] == "KIRIM").sum())
    st.metric("Top 5 → siap kirim", f"{n_kirim} / {len(ev)}")
    for r in ev.itertuples():
        ikon = "✅" if r.keputusan == "KIRIM" else "⛔"
        with st.container(border=True):
            st.markdown(f"### {ikon} #{r.peringkat} {r.nama} — **{r.keputusan}**")
            st.caption(f"{r.toko} · {r.kategori} · skor {r.skor_akhir}")
            for x in r.alasan_lolos:
                st.markdown(f"- ✅ {x}")
            for x in r.alasan_gagal:
                st.markdown(f"- ❌ {x}")
            for x in r.peringatan:
                st.markdown(f"- ⚠️ {x}")

    st.divider()
    st.subheader("Kirim ke antrean n8n Data Table")
    url = st.text_input("URL webhook n8n (Production)", value=os.getenv("N8N_WEBHOOK_URL", ""))
    token = st.text_input("Token (X-M1-Token)", value=os.getenv("N8N_TOKEN", ""), type="password")
    c1, c2 = st.columns(2)
    if c1.button("🔌 Tes koneksi"):
        ok, pesan = n8n_client.tes_koneksi(url, token)
        (st.success if ok else st.error)(pesan)
    siap = ev[ev["keputusan"] == "KIRIM"]
    if c2.button(f"🚀 Kirim {len(siap)} produk KIRIM", type="primary", disabled=siap.empty or not url):
        produk = hasil.set_index("produk_id")
        payloads = [n8n_client.buat_payload(r._asdict(), {**produk.loc[r.produk_id].to_dict(),
                                                         "produk_id": r.produk_id}, tanggal_data)
                    for r in siap.itertuples()]
        for h in n8n_client.kirim(payloads, url, token):
            (st.success if h["ok"] else st.error)(f"{h['kunci']}: {h['pesan']}")
    st.caption("Produk TAHAN tidak pernah dikirim. Kiriman ganda dicegah lewat 'kunci' "
               "(produk_id + tanggal data).")
