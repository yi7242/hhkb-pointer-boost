@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Use the uv-managed Python if present, otherwise the py launcher or pythonw on PATH.
set "PYW=%APPDATA%\uv\python\cpython-3.14-windows-x86_64-none\pythonw.exe"
if not exist "%PYW%" (
  where pyw >nul 2>&1 && (set "PYW=pyw") || (set "PYW=pythonw")
)
start "" "%PYW%" "%~dp0hhkb_pointer_boost.py" --show
