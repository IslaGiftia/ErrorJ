@echo off
cd /d "%~dp0"
set "RUNTIME_PY=C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
set "PYTHON_EXE="
if exist "%RUNTIME_PY%" (
  set "PYTHON_EXE=%RUNTIME_PY%"
)
if defined PYTHON_EXE goto run
where py >nul 2>nul
if %errorlevel%==0 set "PYTHON_EXE=py"
if defined PYTHON_EXE goto run
where python >nul 2>nul
if %errorlevel%==0 set "PYTHON_EXE=python"
if defined PYTHON_EXE goto run
if not defined PYTHON_EXE (
  echo 未检测到可用的 Python，请安装 Python 3.10 或更高版本，或使用 Docker 方式运行。
  pause
  goto :eof
)
:run
call "%~dp0ensure_deps.bat" "%PYTHON_EXE%"
"%PYTHON_EXE%" app.py
