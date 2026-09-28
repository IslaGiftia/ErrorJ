@echo off
cd /d "%~dp0"
set "RUNTIME_PY=C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%RUNTIME_PY%" (
  "%RUNTIME_PY%" app.py
  goto :eof
)
where py >nul 2>nul
if %errorlevel%==0 (
  py app.py
  goto :eof
)
where python >nul 2>nul
if %errorlevel%==0 (
  python app.py
  goto :eof
)
echo 未检测到可用的 Python，请安装 Python 3.10 或更高版本，或使用 Docker 方式运行。
pause
