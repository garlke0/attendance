@echo off
REM The Cafe: double-click to stop everything (your data is kept).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
