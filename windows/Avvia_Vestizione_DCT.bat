@echo off
rem Vestizione DCT - versione portatile (Python ufficiale + programma leggibile in "programma\")
rem I dati restano nella cartella Dati_VestizioneDCT accanto a questa cartella.
chcp 65001 >nul
title Vestizione DCT - non chiudere finche' stai lavorando
"%~dp0python\python.exe" "%~dp0programma\app_windows.py" --browser %*
if errorlevel 1 (
  echo.
  echo Si e' verificato un problema: i dettagli sono qui sopra.
  pause
)
