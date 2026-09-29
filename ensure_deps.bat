@echo off
setlocal
set "PYTHON_EXE=%~1"
if not defined PYTHON_EXE exit /b 0

"%PYTHON_EXE%" -c "import anydoc" >nul 2>nul
if not errorlevel 1 exit /b 0

echo 正在安装 Word/PDF 转换依赖...
"%PYTHON_EXE%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 echo 依赖安装失败，Word/PDF 导入暂不可用。
exit /b 0
