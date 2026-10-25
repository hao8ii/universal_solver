@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" app.py
) else (
    python app.py
)
if errorlevel 1 (
    echo.
    echo 程序异常退出。请查看上方错误信息。
    pause
)
endlocal
