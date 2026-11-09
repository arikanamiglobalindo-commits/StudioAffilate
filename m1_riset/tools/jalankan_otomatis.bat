@echo off
REM jalankan_otomatis.bat - dipakai Windows Task Scheduler (Varian B) atau untuk uji manual.
REM Ubah URL webhook bila port/path n8n Anda berbeda.
cd /d "%~dp0.."
".venv\Scripts\python.exe" run_otomatis.py --maks-kredit 4 --webhook http://localhost:5678/webhook/m1-otomatis
