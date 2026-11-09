"""
run_otomatis.py — Dipanggil n8n (node Execute Command) setiap Senin & Kamis.

Contoh (Windows):
  C:\\affiliate\\m1_riset\\.venv\\Scripts\\python.exe C:\\affiliate\\m1_riset\\run_otomatis.py --maks-kredit 4

Keluaran: SATU baris JSON di stdout (ASCII aman untuk konsol Windows), dibaca node
Code di n8n. Log lengkap ditulis ke data/log_otomatis.txt.
Selalu keluar dengan kode 0 (status gagal ada di JSON) agar n8n tetap mengirim
notifikasi Telegram saat terjadi error.

Opsi --webhook URL: kirim JSON yang sama ke webhook n8n (untuk varian Windows Task Scheduler).
"""
import argparse
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from m1 import db, otomatis  # noqa: E402
from m1.kalodata_api import BASE_URL, KalodataAPI  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Run otomatis M1 (riset + berburu footage seller)")
    ap.add_argument("--maks-kredit", type=float, default=4.0, help="batas kredit per run (default 4)")
    ap.add_argument("--webhook", default="", help="opsional: kirim hasil ke URL webhook n8n")
    ap.add_argument("--jeda-ulang", type=int, default=60, help="detik antar percobaan webhook")
    a = ap.parse_args()
    log = Path(db.DB_PATH).parent / "log_otomatis.txt"
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        api = KalodataAPI(os.getenv("KALODATA_API_KEY", ""),
                          base_url=os.getenv("KALODATA_BASE_URL") or BASE_URL,
                          cache_dir=Path(db.DB_PATH).parent / "api_cache")
        hasil = otomatis.jalankan(api, maks_kredit=a.maks_kredit)
    except Exception as e:  # pengaman terakhir: tetap keluarkan JSON
        hasil = {"status": "gagal", "pesan": f"{e.__class__.__name__}: {e}",
                 "tanggal": datetime.now().date().isoformat(), "kandidat": [], "peringatan": []}
        hasil["telegram_teks"] = otomatis.teks_telegram(hasil)
        with log.open("a", encoding="utf-8") as f:
            f.write(traceback.format_exc())
    with log.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} status={hasil['status']} "
                f"lolos={hasil.get('jumlah_lolos')} kredit={hasil.get('kredit_terpakai')} "
                f"pesan={hasil.get('pesan', '')}\n")
    teks = json.dumps(hasil, ensure_ascii=True, default=str)
    if a.webhook:
        # Docker Desktop/n8n bisa belum siap saat laptop baru menyala -> coba ulang tiap 60 detik (maks 5x).
        # Hasil riset tetap tersimpan lokal walau webhook gagal.
        import time
        import requests
        for coba in range(1, 6):
            try:
                r = requests.post(a.webhook, data=teks, timeout=30,
                                  headers={"Content-Type": "application/json",
                                           "X-M1-Token": os.getenv("N8N_TOKEN", "")})
                pesan = f"webhook HTTP {r.status_code} (percobaan {coba})"
                if r.ok:
                    break
            except requests.RequestException as e:
                pesan = f"webhook gagal percobaan {coba}: {e.__class__.__name__} (n8n/Docker belum jalan?)"
            if coba < 5:
                time.sleep(a.jeda_ulang)
        with log.open("a", encoding="utf-8") as f:
            f.write(pesan + "\n")
    print(teks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
