@echo off
setlocal
cd /d "%~dp0"
echo 正在创建独立运行环境 .venv ...
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 (
        echo 创建虚拟环境失败，请确认已安装 Python 3.9 或更高版本，并加入 PATH。
        pause
        exit /b 1
    )
)
echo 正在安装依赖，首次安装需要联网，可能需要几分钟 ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo 依赖安装失败。可尝试使用国内镜像：
    echo .venv\Scripts\python.exe -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
    pause
    exit /b 1
)
echo.
echo 安装完成。双击"启动通用答题.bat"即可运行。
pause
endlocal
