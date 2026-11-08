@echo off
rem 設定ファイル(.json)をこの bat にドラッグ＆ドロップすると全自動で _converted.iso を作ります
cd /d "%~dp0"
if exist venv\Scripts\activate.bat call venv\Scripts\activate.bat
if "%~1"=="" (
  echo 使い方: run.bat 設定ファイル.json
  pause
  exit /b 1
)
python parofix.py run "%~1"
pause
