@echo off
title Finch Discord Bot Runner
:loop
echo [%DATE% %TIME%] Menjalankan bot Finch...
python main.py
echo [%DATE% %TIME%] Bot berhenti/crash. Restart dalam 5 detik...
timeout /t 5 /nobreak > nul
goto loop